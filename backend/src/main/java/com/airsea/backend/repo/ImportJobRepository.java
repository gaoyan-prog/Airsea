package com.airsea.backend.repo;

import com.airsea.backend.domain.ImportJob;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ImportJobRepository extends JpaRepository<ImportJob, Long> {
    ImportJob findTopByStatusOrderByIdDesc(String status);
}


