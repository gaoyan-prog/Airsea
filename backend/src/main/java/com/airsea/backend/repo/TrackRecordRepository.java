package com.airsea.backend.repo;

import com.airsea.backend.domain.TrackRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface TrackRecordRepository extends JpaRepository<TrackRecord, Long> {
    List<TrackRecord> findTop20ByTrackingNoOrderByIdDesc(String trackingNo);
}


