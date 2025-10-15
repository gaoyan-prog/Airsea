package com.airsea.backend.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "track_records")
@Getter
@Setter
@NoArgsConstructor
public class TrackRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String carrierCode;

    @Column(nullable = false, length = 255)
    private String trackingNo;

    @Column(length = 64)
    private String eta; // 直接以字符串保存 ISO 或带时区时间

    @Column(length = 255)
    private String description; // 例如: Vessel Arrival
}


