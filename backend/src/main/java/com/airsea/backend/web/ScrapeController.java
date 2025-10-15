package com.airsea.backend.web;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/scrape")
public class ScrapeController {

    @GetMapping(value = "/wanhai/{number}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, Object>> runWanHai(@org.springframework.web.bind.annotation.PathVariable("number") String number) {
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(ScrapeController.class);
        try {
            // 解析脚本绝对路径（兼容从项目根或 backend 目录启动）
            File prefer = new File("wanhai_tracking_playwright.py");
            File fallback = new File("backend/wanhai_tracking_playwright.py");
            File script = prefer.exists() ? prefer : fallback;
            if (!script.exists()) {
                throw new FileNotFoundException("python script not found: " + script.getAbsolutePath());
            }

            // 构造命令
            List<String> cmd = List.of("python", script.getPath(), "--number", number);
            log.debug("[scrape] exec: {}", cmd);

            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(false);
            Process p = pb.start();

            // 读取输出
            String stdout = readFully(p.getInputStream());
            String stderr = readFully(p.getErrorStream());

            boolean finished = p.waitFor(Duration.ofSeconds(180).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
            if (!finished) {
                p.destroyForcibly();
                return ResponseEntity.status(504).body(Map.of(
                        "ok", false,
                        "error", "python process timeout",
                        "stderr", truncate(stderr),
                        "stdout", truncate(stdout)
                ));
            }

            int code = p.exitValue();
            log.debug("[scrape] exitCode={} stderrSnippet={}", code, truncate(stderr));

            Map<String, Object> payload = tryParseJson(stdout);
            if (payload == null) {
                payload = new LinkedHashMap<>();
                payload.put("ok", code == 0);
                payload.put("raw", truncate(stdout));
                if (!stderr.isBlank()) payload.put("stderr", truncate(stderr));
            }
            return ResponseEntity.ok(payload);
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of(
                    "ok", false,
                    "error", e.getMessage()
            ));
        }
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

    @SuppressWarnings("unchecked")
    private Map<String, Object> tryParseJson(String s) {
        if (s == null || s.isBlank()) return null;
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            om.findAndRegisterModules();
            return om.readValue(s, java.util.LinkedHashMap.class);
        } catch (Exception ignore) {
            return null;
        }
    }
}

