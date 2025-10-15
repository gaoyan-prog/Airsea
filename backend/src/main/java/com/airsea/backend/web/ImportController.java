package com.airsea.backend.web;

import com.airsea.backend.service.ImportService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/import")
public class ImportController {
    private final ImportService importService;

    public ImportController(ImportService importService) {
        this.importService = importService;
    }

    @PostMapping("/start")
    public ResponseEntity<Map<String, Object>> start() {
        return ResponseEntity.ok(importService.start());
    }

    @GetMapping("/status/{jobId}")
    public ResponseEntity<Map<String, Object>> status(@PathVariable("jobId") long jobId) {
        return ResponseEntity.ok(importService.status(jobId));
    }

    @GetMapping("/active")
    public ResponseEntity<Map<String, Object>> active() {
        return ResponseEntity.ok(importService.active());
    }
}


