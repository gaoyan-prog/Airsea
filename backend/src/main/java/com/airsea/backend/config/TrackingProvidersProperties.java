package com.airsea.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
@ConfigurationProperties(prefix = "app.tracking")
public class TrackingProvidersProperties {
    private List<Provider> providers;

    public List<Provider> getProviders() {
        return providers;
    }

    public void setProviders(List<Provider> providers) {
        this.providers = providers;
    }

    public static class Provider {
        private String carrierCode;
        private String displayName;
        private String method = "GET";
        private String urlTemplate;
        private String baseUrl; // 可选，若 urlTemplate 以 / 开头则会拼接
        private Map<String, String> headers; // optional
        private String bodyTemplateJson; // for POST
        private String parser; // e.g. EVER_EVENTS
        private Boolean enabled = true;
        private String apiKey; // stored in yml or env

        public String getCarrierCode() { return carrierCode; }
        public void setCarrierCode(String carrierCode) { this.carrierCode = carrierCode; }
        public String getDisplayName() { return displayName; }
        public void setDisplayName(String displayName) { this.displayName = displayName; }
        public String getMethod() { return method; }
        public void setMethod(String method) { this.method = method; }
        public String getUrlTemplate() { return urlTemplate; }
        public void setUrlTemplate(String urlTemplate) { this.urlTemplate = urlTemplate; }
        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
        public Map<String, String> getHeaders() { return headers; }
        public void setHeaders(Map<String, String> headers) { this.headers = headers; }
        public String getBodyTemplateJson() { return bodyTemplateJson; }
        public void setBodyTemplateJson(String bodyTemplateJson) { this.bodyTemplateJson = bodyTemplateJson; }
        public String getParser() { return parser; }
        public void setParser(String parser) { this.parser = parser; }
        public Boolean getEnabled() { return enabled; }
        public void setEnabled(Boolean enabled) { this.enabled = enabled; }
        public String getApiKey() { return apiKey; }
        public void setApiKey(String apiKey) { this.apiKey = apiKey; }
    }
}


