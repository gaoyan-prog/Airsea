package com.airsea.backend.domain;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "shipments")
@Getter
@Setter
@NoArgsConstructor
public class Shipment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String company;

    @Column(name = "tracking_no", nullable = false, length = 255)
    @JsonProperty("tracking_no")
    private String trackingNo;

    @Column(nullable = false, length = 64)
    private String status = "Created";

    @Column
    private Integer pieces = 1;
}


