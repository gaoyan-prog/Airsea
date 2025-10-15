package com.airsea.backend.repo;

import com.airsea.backend.domain.Shipment;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ShipmentRepository extends JpaRepository<Shipment, Long> {
    List<Shipment> findTop50ByTrackingNoContainingIgnoreCaseOrderByIdDesc(String trackingNo);
}


