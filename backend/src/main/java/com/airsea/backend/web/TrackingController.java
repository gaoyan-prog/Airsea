package com.airsea.backend.web;

import com.airsea.backend.domain.CarrierApiConfig;
import com.airsea.backend.repo.CarrierApiConfigRepository;
import com.airsea.backend.repo.TrackRecordRepository;
import com.airsea.backend.service.TrackingService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CopyOnWriteArrayList;

@RestController
@RequestMapping("/tracking")
public class TrackingController {
    // 全局活动资源（简单实现：杀死所有活动任务）
    private static final CopyOnWriteArrayList<java.util.concurrent.ExecutorService> ACTIVE_EXECUTORS = new CopyOnWriteArrayList<>();
    private static final CopyOnWriteArrayList<Process> ACTIVE_PY_PROCS = new CopyOnWriteArrayList<>();

    private final TrackingService trackingService;
    private final CarrierApiConfigRepository configRepository;
    private final TrackRecordRepository recordRepository;

    public TrackingController(TrackingService trackingService,
                              CarrierApiConfigRepository configRepository,
                              TrackRecordRepository recordRepository) {
        this.trackingService = trackingService;
        this.configRepository = configRepository;
        this.recordRepository = recordRepository;
    }

    // 保存/更新某承运商的 API 配置
    @PostMapping("/config")
    public CarrierApiConfig saveConfig(@RequestBody CarrierApiConfig in) {
        if (in.getEnabled() == null) in.setEnabled(true);
        return configRepository.save(in);
    }

    @GetMapping("/config/{carrierCode}")
    public CarrierApiConfig getConfig(@PathVariable String carrierCode) {
        return configRepository.findByCarrierCodeAndEnabledTrue(carrierCode);
    }

    // 执行查询：指定 carrier、trackingNo、apiKey
    @PostMapping("/query")
    public ResponseEntity<Map<String, Object>> query(@RequestBody Map<String, Object> body) {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        String carrier = String.valueOf(body.get("carrier"));
        String trackingNo = String.valueOf(body.get("trackingNo"));
        String apiKey = null; // API Key 统一从 application.yml 读取，不从前端传
        Map<String, Object> extra = null;
        Object extraObj = body.get("extra");
        if (extraObj instanceof Map<?,?> m) {
            java.util.Map<String, Object> tmp = new java.util.HashMap<>();
            for (java.util.Map.Entry<?,?> e : m.entrySet()) {
                tmp.put(String.valueOf(e.getKey()), e.getValue());
            }
            extra = tmp;
        }
        log.debug("[tracking] single query carrier={} trackingNo={}", carrier, trackingNo);
        return ResponseEntity.ok(trackingService.queryAndSave(carrier, trackingNo, apiKey, extra));
    }

    // 只传 trackingNo，自动并发查询所有已启用的公司，返回有结果的
    @GetMapping("/query-all/{trackingNo}")
    public List<Map<String, Object>> queryAll(@PathVariable("trackingNo") String trackingNo) {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        log.debug("[tracking] query-all start, trackingNo={}", trackingNo);

        java.util.concurrent.ExecutorService exec = java.util.concurrent.Executors.newFixedThreadPool(3);
        ACTIVE_EXECUTORS.add(exec);
        java.util.concurrent.atomic.AtomicReference<Process> pyWanRef = new java.util.concurrent.atomic.AtomicReference<>();
        java.util.concurrent.atomic.AtomicReference<Process> pyShipRef = new java.util.concurrent.atomic.AtomicReference<>();
        java.util.concurrent.ExecutorCompletionService<Map<String, Object>> cs =
                new java.util.concurrent.ExecutorCompletionService<>(exec);

        long t0 = System.currentTimeMillis();
        java.util.concurrent.Future<Map<String, Object>> fJava = cs.submit(() -> {
            long s = System.currentTimeMillis();
            try {
                List<Map<String, Object>> rs = trackingService.queryAllProvidersAndSave(trackingNo);
                Map<String, Object> row = (rs != null && !rs.isEmpty()) ? rs.get(0) : null;
                log.debug("[tracking] java-aggregate finished in {}ms, valid={}", System.currentTimeMillis()-s, isValidRow(row));
                return row;
            } catch (Exception e) {
                log.debug("[tracking] java-aggregate error: {}", e.getMessage());
                return null;
            }
        });
        java.util.concurrent.Future<Map<String, Object>> fWan = cs.submit(() -> {
            long s = System.currentTimeMillis();
            Map<String, Object> row = runWanHaiScrapeWithProcess(trackingNo, pyWanRef);
            log.debug("[tracking] python-wanhai finished in {}ms, valid={}", System.currentTimeMillis()-s, isValidRow(row));
            return row;
        });
        java.util.concurrent.Future<Map<String, Object>> fShip = cs.submit(() -> {
            long s = System.currentTimeMillis();
            Map<String, Object> row = runShipmentlinkScrapeWithProcess(trackingNo, pyShipRef);
            log.debug("[tracking] python-shipmentlink finished in {}ms, valid={}", System.currentTimeMillis()-s, isValidRow(row));
            return row;
        });

        Map<String, Object> winner = null;
        String winnerSource = null; // "java" | "wanhai" | "shipmentlink"
        int completed = 0;
        long timeoutMs = 180_000; // 180s
        final long softWaitMs = 2500; // Java 先返回时，给 Python 的软等待窗口
        Map<String, Object> javaCandidate = null; long javaCandidateAt = 0L;
        try {
            while (completed < 3) {
                java.util.concurrent.Future<Map<String, Object>> f = cs.poll(500, java.util.concurrent.TimeUnit.MILLISECONDS);
                long now = System.currentTimeMillis();
                if (javaCandidate != null && (now - javaCandidateAt) >= softWaitMs) { winner = javaCandidate; winnerSource = "java"; break; }
                if (f == null) { if (now - t0 > timeoutMs) break; else continue; }
                completed++;
                Map<String, Object> r = safeGet(f);
                boolean valid = isValidRow(r);
                String src = (f == fJava) ? "java" : (f == fWan ? "wanhai" : (f == fShip ? "shipmentlink" : "unknown"));
                log.debug("[tracking] task completed {}/3, src={}, valid={}", completed, src, valid);
                if (!valid) continue;
                if (src.equals("wanhai") || src.equals("shipmentlink")) { winner = r; winnerSource = src; break; }
                if (src.equals("java")) { javaCandidate = r; javaCandidateAt = now; log.debug("[tracking] java candidate ready, soft-wait {}ms", softWaitMs); }
            }
            if (winner == null && javaCandidate != null) { winner = javaCandidate; winnerSource = "java"; log.debug("[tracking] soft-wait ended, fallback to java candidate"); }
        } catch (InterruptedException ignore) {
        } finally {
            // 取消并清理
            exec.shutdownNow();
            ACTIVE_EXECUTORS.remove(exec);
            if ("java".equals(winnerSource)) {
                Process pw = pyWanRef.get();
                if (pw != null && pw.isAlive()) { pw.destroyForcibly(); log.debug("[tracking] wanhai python destroyed because java won"); }
                Process ps = pyShipRef.get();
                if (ps != null && ps.isAlive()) { ps.destroyForcibly(); log.debug("[tracking] shipmentlink python destroyed because java won"); }
            } else if ("wanhai".equals(winnerSource)) {
                // 取消 Java；结束另一个 Python（shipmentlink）
                try { fJava.cancel(true); } catch (Exception ignore) {}
                Process ps = pyShipRef.get();
                if (ps != null && ps.isAlive()) { ps.destroyForcibly(); log.debug("[tracking] shipmentlink python destroyed because wanhai won"); }
            } else if ("shipmentlink".equals(winnerSource)) {
                try { fJava.cancel(true); } catch (Exception ignore) {}
                Process pw = pyWanRef.get();
                if (pw != null && pw.isAlive()) { pw.destroyForcibly(); log.debug("[tracking] wanhai python destroyed because shipmentlink won"); }
            }
            log.debug("[tracking] query-all finished in {}ms, winner={} source={}",
                    System.currentTimeMillis()-t0, winner != null, winnerSource);
        }

        if (winner == null) return java.util.List.of();
        return java.util.List.of(winner);
    }

    // 调试用：返回每个 provider 的状态码、最终URL和响应片段
    @GetMapping("/query-all-debug/{trackingNo}")
    public List<Map<String, Object>> queryAllDebug(@PathVariable("trackingNo") String trackingNo) {
        return trackingService.queryAllProvidersDebug(trackingNo);
    }

    // 查看某单号最近的标准化记录
    @GetMapping("/records/{trackingNo}")
    public List<?> listRecords(@PathVariable String trackingNo) {
        return recordRepository.findTop20ByTrackingNoOrderByIdDesc(trackingNo);
    }

    // --- embed python scrape ---
    private Map<String, Object> runWanHaiScrapeWithProcess(String number, java.util.concurrent.atomic.AtomicReference<Process> procRef) throws Exception {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        File prefer = new File("wanhai_tracking_playwright.py");
        File fallback = new File("backend/wanhai_tracking_playwright.py");
        File script = prefer.exists() ? prefer : fallback;
        if (!script.exists()) {
            log.debug("[tracking] python script not found: {}", script.getAbsolutePath());
            return null;
        }
        java.util.List<String> cmd = java.util.List.of("python", script.getPath(), "--number", number);
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(false);
        Process p = pb.start();
        if (procRef != null) procRef.set(p);
        ACTIVE_PY_PROCS.add(p);

        // 仅以 stdout 作为数据源，stderr 用于日志，不混淆 JSON
        // 实时转发 stderr 便于观察 Python 执行过程
        Thread stderrThread = new Thread(() -> streamToLog(p.getErrorStream(), "wanhai"));
        stderrThread.setDaemon(true);
        stderrThread.start();
        String stdout = readFully(p.getInputStream());
        String stderr = readFully(p.getErrorStream());
        boolean finished = p.waitFor(Duration.ofSeconds(180).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
        if (!finished) {
            p.destroyForcibly();
            log.debug("[tracking] python scrape timeout, stderrSnippet={}", truncate(stderr));
            return null;
        }
        int code = p.exitValue();
        log.debug("[tracking] python scrape exitCode={} stderrSnippet={} stdoutSnippet={}", code, truncate(stderr), truncate(stdout));
        ACTIVE_PY_PROCS.remove(p);
        Map<String, Object> payload = tryParseJson(stdout);
        if (payload == null) return null;
        Object status = payload.get("status");
        if (status == null || !"ok".equalsIgnoreCase(String.valueOf(status))) return null;
        String resultText = payload.get("result") == null ? null : String.valueOf(payload.get("result")).trim();
        if (resultText != null) resultText = resultText.replace('/', '-');
        if (resultText == null || resultText.isBlank()) return null;
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("carrier", "WANHAI");
        row.put("eta", resultText);
        row.put("description", "/");
        row.put("trackingNo", number);
        return row;
    }

    private Map<String, Object> runShipmentlinkScrapeWithProcess(String number, java.util.concurrent.atomic.AtomicReference<Process> procRef) throws Exception {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        File prefer = new File("shipmentlink_tracking_playwright.py");
        File fallback = new File("backend/shipmentlink_tracking_playwright.py");
        File script = prefer.exists() ? prefer : fallback;
        if (!script.exists()) {
            log.debug("[tracking] python script not found: {}", script.getAbsolutePath());
            return null;
        }
        java.util.List<String> cmd = java.util.List.of("python", script.getPath(), "--number", number);
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(false);
        Process p = pb.start();
        if (procRef != null) procRef.set(p);
        ACTIVE_PY_PROCS.add(p);

        Thread stderrThread2 = new Thread(() -> streamToLog(p.getErrorStream(), "shipmentlink"));
        stderrThread2.setDaemon(true);
        stderrThread2.start();
        String stdout = readFully(p.getInputStream());
        String stderr = readFully(p.getErrorStream());
        boolean finished = p.waitFor(Duration.ofSeconds(180).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
        if (!finished) {
            p.destroyForcibly();
            log.debug("[tracking] shipmentlink python timeout, stderrSnippet={}", truncate(stderr));
            return null;
        }
        int code = p.exitValue();
        log.debug("[tracking] shipmentlink python exitCode={} stderrSnippet={} stdoutSnippet={}", code, truncate(stderr), truncate(stdout));
        ACTIVE_PY_PROCS.remove(p);
        Map<String, Object> payload = tryParseJson(stdout);
        if (payload == null) return null;
        Object status = payload.get("status");
        if (status == null || !"ok".equalsIgnoreCase(String.valueOf(status))) return null;
        String resultText = payload.get("result") == null ? null : String.valueOf(payload.get("result")).trim();
        if (resultText != null) resultText = resultText.replace('/', '-');
        if (resultText == null || resultText.isBlank()) return null;
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("carrier", "SHIPMENTLINK");
        row.put("eta", resultText);
        row.put("description", "/");
        row.put("trackingNo", number);
        return row;
    }

    // 手动取消：杀死所有活动线程与 Python 进程
    @PostMapping("/query-all/cancel")
    public Map<String, Object> cancelAll() {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        int killedProc = 0;
        for (Process p : ACTIVE_PY_PROCS) {
            try { if (p != null && p.isAlive()) { p.destroyForcibly(); killedProc++; } } catch (Exception ignore) {}
        }
        ACTIVE_PY_PROCS.clear();
        int shutExec = 0;
        for (var ex : ACTIVE_EXECUTORS) {
            try { ex.shutdownNow(); shutExec++; } catch (Exception ignore) {}
        }
        ACTIVE_EXECUTORS.clear();
        log.debug("[tracking] cancel-all done, killedProc={} shutExec={}", killedProc, shutExec);
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("ok", true);
        resp.put("killedProc", killedProc);
        resp.put("shutExecutors", shutExec);
        return resp;
    }

    private boolean isValidRow(Map<String, Object> row) {
        if (row == null) return false;
        Object eta = row.get("eta");
        return eta != null && !String.valueOf(eta).isBlank();
    }

    private <T> T safeGet(java.util.concurrent.Future<T> f) {
        try { return f.get(); } catch (Exception ignore) { return null; }
    }

    private String readFully(InputStream in) throws IOException {
        try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line).append('\n');
            }
            return sb.toString();
        }
    }

    private String truncate(String s) {
        if (s == null) return null;
        return s.length() > 400 ? s.substring(0, 400) : s;
    }

    private void streamToLog(InputStream in, String tag) {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingController.class);
        try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                log.info("[py:{}] {}", tag, line);
            }
        } catch (Exception ignore) {}
    }

    private Map<String, Object> tryParseJson(String s) {
        if (s == null || s.isBlank()) return null;
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            om.findAndRegisterModules();
            com.fasterxml.jackson.core.type.TypeReference<java.util.LinkedHashMap<String, Object>> tr =
                    new com.fasterxml.jackson.core.type.TypeReference<>() {};
            return om.readValue(s, tr);
        } catch (Exception ignore) {
            return null;
        }
    }
}


