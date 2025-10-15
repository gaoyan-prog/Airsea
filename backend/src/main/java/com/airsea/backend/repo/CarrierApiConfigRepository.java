package com.airsea.backend.repo;

import com.airsea.backend.domain.CarrierApiConfig;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CarrierApiConfigRepository extends JpaRepository<CarrierApiConfig, Long> {
    CarrierApiConfig findByCarrierCodeAndEnabledTrue(String carrierCode);
}


