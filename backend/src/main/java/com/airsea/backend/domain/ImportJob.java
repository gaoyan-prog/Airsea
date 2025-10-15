package com.airsea.backend.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "import_jobs")
@Getter
@Setter
@NoArgsConstructor
public class ImportJob {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 64)
    private String gasJobId;

    @Column(length = 16)
    private String status; // running | success | failed

    @Column(length = 32)
    private String phase;

    @Column(columnDefinition = "TEXT")
    private String error;

    @Column(columnDefinition = "TEXT")
    private String lastLog;

    @Column(length = 64)
    private String startedAt;

    @Column(length = 64)
    private String finishedAt;
}


