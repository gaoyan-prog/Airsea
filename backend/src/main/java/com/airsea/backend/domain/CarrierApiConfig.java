package com.airsea.backend.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "carrier_api_configs")
@Getter
@Setter
@NoArgsConstructor
public class CarrierApiConfig {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64, unique = true)
    private String carrierCode; // 例如: EVER, MAERSK

    @Column(length = 128)
    private String displayName;

    @Column(nullable = false, length = 8)
    private String method; // GET | POST

    @Column(nullable = false, length = 1024)
    private String urlTemplate; // 例如: /api/.../%2Fevents%2F{trackingNo}%3Flimit%3D100/{apiKey}

    @Column(columnDefinition = "TEXT")
    private String headersJson; // 可为空, JSON 对象字符串, 支持占位符

    @Column(columnDefinition = "TEXT")
    private String bodyTemplateJson; // POST 时使用, 支持占位符

    @Column(length = 64)
    private String parser; // 针对不同公司选择解析器, 例如: EVER_EVENTS

    @Column
    private Boolean enabled = true;
}


