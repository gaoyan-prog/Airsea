package com.airsea.backend.service;

import com.airsea.backend.domain.CarrierApiConfig;
import com.airsea.backend.domain.TrackRecord;
import com.airsea.backend.repo.CarrierApiConfigRepository;
import com.airsea.backend.repo.TrackRecordRepository;
import com.airsea.backend.config.TrackingProvidersProperties;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;

@Service
public class TrackingService {
    private final RestTemplate restTemplate;
    private final CarrierApiConfigRepository configRepository;
    private final TrackingProvidersProperties providersProperties;
    private final TrackRecordRepository recordRepository;

    public TrackingService(RestTemplate restTemplate,
                           CarrierApiConfigRepository configRepository,
                           TrackRecordRepository recordRepository,
                           TrackingProvidersProperties providersProperties) {
        this.restTemplate = restTemplate;
        this.configRepository = configRepository;
        this.recordRepository = recordRepository;
        this.providersProperties = providersProperties;
    }

    public Map<String, Object> queryAndSave(String carrierCode, String trackingNo, String apiKey, Map<String, Object> extra) {
        CarrierApiConfig cfg = configRepository.findByCarrierCodeAndEnabledTrue(carrierCode);
        if (cfg == null) {
            // 若数据库未配置，则尝试从 application.yml 的 providers 中读取一次性配置
            var opt = providersProperties.getProviders() == null ? null : providersProperties.getProviders().stream()
                    .filter(p -> Boolean.TRUE.equals(p.getEnabled()) && p.getCarrierCode().equalsIgnoreCase(carrierCode))
                    .findFirst().orElse(null);
            if (opt == null) throw new IllegalArgumentException("carrier config not found: " + carrierCode);
            cfg = new CarrierApiConfig();
            cfg.setCarrierCode(opt.getCarrierCode());
            cfg.setDisplayName(opt.getDisplayName());
            cfg.setMethod(opt.getMethod());
            cfg.setUrlTemplate(opt.getUrlTemplate());
            cfg.setHeadersJson(opt.getHeaders() == null ? null : toJson(opt.getHeaders()));
            cfg.setBodyTemplateJson(opt.getBodyTemplateJson());
            cfg.setParser(opt.getParser());
            cfg.setEnabled(true);
            // 不落库，直接使用
            apiKey = apiKey == null ? opt.getApiKey() : apiKey;
        }

        String url = buildUrl(cfg.getUrlTemplate(), trackingNo, apiKey, extra);
        if (url.startsWith("/") && providersProperties.getProviders() != null) {
            var opt = providersProperties.getProviders().stream()
                    .filter(p -> p.getCarrierCode().equalsIgnoreCase(carrierCode))
                    .findFirst().orElse(null);
            if (opt != null && opt.getBaseUrl() != null && !opt.getBaseUrl().isBlank()) {
                url = opt.getBaseUrl().replaceAll("/+$", "") + url;
            }
        }
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TrackingService.class);
        HttpMethod method;
        try {
            method = HttpMethod.valueOf(cfg.getMethod() == null ? "GET" : cfg.getMethod().toUpperCase());
        } catch (Exception ignore) {
            method = HttpMethod.GET;
        }
        log.debug("[tracking] carrier={} method={} url={}", carrierCode, method, url);

        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON, MediaType.TEXT_PLAIN));
        if (cfg.getHeadersJson() != null && !cfg.getHeadersJson().isBlank()) {
            Map<String, Object> hs = parseJsonObject(cfg.getHeadersJson());
            for (var e : hs.entrySet()) {
                String hv = String.valueOf(e.getValue());
                hv = hv.replace("{trackingNo}", trackingNo)
                        .replace("{apiKey}", apiKey == null ? "" : apiKey);
                headers.set(e.getKey(), hv);
            }
        }

        String bodyStr = null;
        if (method == HttpMethod.POST && cfg.getBodyTemplateJson() != null && !cfg.getBodyTemplateJson().isBlank()) {
            bodyStr = cfg.getBodyTemplateJson()
                    .replace("{trackingNo}", trackingNo)
                    .replace("{apiKey}", apiKey == null ? "" : apiKey);
        }
        HttpEntity<String> entity = bodyStr == null ? new HttpEntity<>(headers) : new HttpEntity<>(bodyStr, headers);

        // 注意：urlTemplate 中包含已编码的 %2F 等，使用 URI 以避免 RestTemplate 再次编码导致 %252F
        ResponseEntity<String> resp = restTemplate.exchange(java.net.URI.create(url), method, entity, String.class);
        int statusCode = resp.getStatusCodeValue();
        log.debug("[tracking] carrier={} status={}", carrierCode, statusCode);
        String raw = resp.getBody();
        log.debug("[tracking] carrier={} rawBodySnippet={}", carrierCode, raw != null ? raw.substring(0, Math.min(400, raw.length())) : "null");

        // 解析：数组中优先找 internalEventLabel == "Vessel Arrival"；
        // 其次找 transportEventTypeCode == "ARRI"；再次找 internalEventCode == "PVA"（计划靠港）
        String eta = parseEta(cfg.getParser(), raw);
        log.debug("[tracking] carrier={} parsedEta={}", carrierCode, eta);
        TrackRecord rec = new TrackRecord();
        rec.setCarrierCode(carrierCode);
        rec.setTrackingNo(trackingNo);
        rec.setEta(eta);
        rec.setDescription("Vessel Arrival");
        recordRepository.save(rec);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", true);
        out.put("eta", eta);
        out.put("savedId", rec.getId());
        out.put("raw", raw);
        out.put("url", url);
        out.put("statusCode", statusCode);
        return out;
    }

    public List<Map<String, Object>> queryAllProvidersAndSave(String trackingNo) {
        List<Map<String, Object>> results = new ArrayList<>();
        List<TrackingProvidersProperties.Provider> providers = providersProperties.getProviders();
        if (providers == null) return results;
        for (var p : providers) {
            if (!Boolean.TRUE.equals(p.getEnabled())) continue;
            try {
                Map<String, Object> r = queryAndSave(p.getCarrierCode(), trackingNo, p.getApiKey(), null);
                String eta = r.get("eta") == null ? null : String.valueOf(r.get("eta"));
                if (eta != null && !eta.isBlank()) {
                    results.add(Map.of(
                            "carrier", p.getCarrierCode(),
                            "eta", eta,
                            "description", "Vessel Arrival"
                    ));
                } else {
                    Object raw = r.get("raw");
                    if (raw instanceof String s && s.trim().startsWith("[") && s.trim().length() > 2) {
                        results.add(Map.of(
                                "carrier", p.getCarrierCode(),
                                "eta", "",
                                "description", "Found events (ETA not parsed)"
                        ));
                    }
                }
            } catch (Exception ignore) {}
        }
        return results;
    }

    public List<Map<String, Object>> queryAllProvidersDebug(String trackingNo) {
        List<Map<String, Object>> results = new ArrayList<>();
        List<TrackingProvidersProperties.Provider> providers = providersProperties.getProviders();
        if (providers == null) return results;
        for (var p : providers) {
            if (!Boolean.TRUE.equals(p.getEnabled())) continue;
            try {
                Map<String, Object> r = queryAndSave(p.getCarrierCode(), trackingNo, p.getApiKey(), null);
                String eta = r.get("eta") == null ? null : String.valueOf(r.get("eta"));
                String snippet = null;
                Object raw = r.get("raw");
                if (raw instanceof String s) snippet = s.substring(0, Math.min(400, s.length()));
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("carrier", p.getCarrierCode());
                row.put("statusCode", r.get("statusCode"));
                row.put("url", r.get("url"));
                row.put("eta", eta);
                row.put("rawSnippet", snippet);
                results.add(row);
            } catch (Exception e) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("carrier", p.getCarrierCode());
                row.put("error", e.getMessage());
                results.add(row);
            }
        }
        return results;
    }

    private String buildUrl(String tpl, String trackingNo, String apiKey, Map<String, Object> extra) {
        String url = tpl.replace("{trackingNo}", urlEncode(trackingNo))
                .replace("{apiKey}", apiKey == null ? "" : urlEncode(apiKey));
        if (extra != null) for (var e : extra.entrySet()) {
            url = url.replace("{" + e.getKey() + "}", urlEncode(String.valueOf(e.getValue())));
        }
        return url;
    }

    private String urlEncode(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }

    private Map<String, Object> parseJsonObject(String json) {
        try {
            com.fasterxml.jackson.core.type.TypeReference<java.util.Map<String, Object>> tr =
                    new com.fasterxml.jackson.core.type.TypeReference<>() {};
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(json, tr);
        } catch (Exception e) {
            return java.util.Map.of();
        }
    }

    private String parseEta(String parser, String raw) {
        if (raw == null || raw.isBlank()) return null;
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            om.findAndRegisterModules();
            if (raw.trim().startsWith("[")) {
                com.fasterxml.jackson.core.type.TypeReference<java.util.List<java.util.Map<String, Object>>> tr =
                        new com.fasterxml.jackson.core.type.TypeReference<>() {};
                java.util.List<java.util.Map<String, Object>> arr = om.readValue(raw, tr);
                for (var item : arr) {
                    Object carrierSpecificData = item.get("carrierSpecificData");
                    if (carrierSpecificData instanceof Map csd) {
                        Object label = csd.get("internalEventLabel");
                        if (label != null && String.valueOf(label).equalsIgnoreCase("Vessel Arrival")) {
                            Object dt = item.get("eventDateTime");
                            return dt != null ? String.valueOf(dt) : null;
                        }
                    }
                }
                // 其次根据 transportEventTypeCode == ARRI
                for (var item : arr) {
                    Object code = item.get("transportEventTypeCode");
                    if (code != null && String.valueOf(code).equalsIgnoreCase("ARRI")) {
                        Object dt = item.get("eventDateTime");
                        if (dt != null) return String.valueOf(dt);
                    }
                }
                // 再次根据 internalEventCode == PVA（计划靠港）
                for (var item : arr) {
                    Object carrierSpecificData = item.get("carrierSpecificData");
                    if (carrierSpecificData instanceof Map csd) {
                        Object ev = csd.get("internalEventCode");
                        if (ev != null && String.valueOf(ev).equalsIgnoreCase("PVA")) {
                            Object dt = item.get("eventDateTime");
                            if (dt != null) return String.valueOf(dt);
                        }
                    }
                }
            } else {
                // 其他结构的解析可在此扩展
            }
        } catch (Exception ignore) {}
        return null;
    }

    private String toJson(Object o) {
        try { return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(o); }
        catch (Exception e) { return null; }
    }
}


