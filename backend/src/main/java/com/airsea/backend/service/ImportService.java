package com.airsea.backend.service;

import com.airsea.backend.domain.ImportJob;
import com.airsea.backend.repo.ImportJobRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;

@Service
public class ImportService {
    private final RestTemplate restTemplate;
    private final ImportJobRepository importJobRepository;

    @Value("${app.gas.url}")
    private String gasUrl;

    public ImportService(RestTemplate restTemplate, ImportJobRepository importJobRepository) {
        this.restTemplate = restTemplate;
        this.importJobRepository = importJobRepository;
    }

    public Map<String, Object> start() {
        Map<String, Object> body = new HashMap<>();
        body.put("action", "startRunAll");
        Map resp = postJson(body);
        ImportJob job = new ImportJob();
        job.setStatus("running");
        job.setPhase("init");
        // 兼容 GAS 返回 gasJobId 或 jobId
        if (resp != null) {
            Object gasId = resp.get("gasJobId") != null ? resp.get("gasJobId") : resp.get("jobId");
            if (gasId != null) job.setGasJobId(String.valueOf(gasId));
        }
        importJobRepository.save(job);
        Map<String, Object> out = new HashMap<>();
        out.put("ok", true);
        out.put("jobId", job.getId());
        out.put("gasJobId", job.getGasJobId());
        return out;
    }

    public Map<String, Object> status(long jobId) {
        // 读取 DB；查不到直接报错，不创建空记录
        ImportJob job = importJobRepository.findById(jobId)
                .orElseThrow(() -> new IllegalArgumentException("job not found: " + jobId));

        Map<String, Object> body = new HashMap<>();
        body.put("action", "status");
        if (job.getGasJobId() != null) body.put("jobId", job.getGasJobId());
        Map resp = postJson(body);

        if (resp != null) {
            Object status = resp.get("status");
            Object phase = resp.get("phase");
            Object lastLog = resp.get("lastLog");
            Object startedAt = resp.get("startedAt");
            Object finishedAt = resp.get("finishedAt");
            Object error = resp.get("error");
            job.setStatus(status != null ? status.toString() : job.getStatus());
            job.setPhase(phase != null ? phase.toString() : job.getPhase());
            job.setLastLog(lastLog != null ? lastLog.toString() : job.getLastLog());
            job.setStartedAt(startedAt != null ? startedAt.toString() : job.getStartedAt());
            job.setFinishedAt(finishedAt != null ? finishedAt.toString() : job.getFinishedAt());
            job.setError(error != null ? error.toString() : job.getError());
            importJobRepository.save(job);
        }
        Map<String, Object> out = new HashMap<>();
        out.put("jobId", jobId);
        out.put("gasJobId", job.getGasJobId());
        out.put("data", resp);
        return out;
    }

    public Map<String, Object> active() {
        ImportJob job = importJobRepository.findTopByStatusOrderByIdDesc("running");
        if (job == null) return java.util.Map.of("ok", false);
        java.util.Map<String, Object> out = new java.util.LinkedHashMap<>();
        out.put("ok", true);
        out.put("jobId", job.getId());
        out.put("status", job.getStatus());
        if (job.getGasJobId() != null) out.put("gasJobId", job.getGasJobId());
        if (job.getPhase() != null) out.put("phase", job.getPhase());
        if (job.getLastLog() != null) out.put("lastLog", job.getLastLog());
        return out;
    }

    private Map postJson(Map<String, Object> payload) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON, MediaType.TEXT_PLAIN, MediaType.TEXT_HTML));
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(payload, headers);
        try {
            var resp = restTemplate.postForEntity(gasUrl, entity, String.class);
            String body = resp.getBody();
            if (body == null || body.isBlank()) {
                return java.util.Map.of("ok", false, "error", "empty body", "statusCode", resp.getStatusCodeValue());
            }
            // 优先按 JSON 解析；若非 JSON，则作为原始文本返回
            try {
                com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
                Object obj = om.readValue(body, java.util.Map.class);
                return (java.util.Map) obj;
            } catch (Exception ignore) {
                return java.util.Map.of("ok", false, "raw", body, "statusCode", resp.getStatusCodeValue());
            }
        } catch (Exception e) {
            throw new RuntimeException("GAS request failed: " + e.getMessage(), e);
        }
    }
}


