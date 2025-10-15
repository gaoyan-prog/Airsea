package com.airsea.backend.web;

import com.airsea.backend.domain.Shipment;
import com.airsea.backend.repo.ShipmentRepository;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;

@RestController
@Validated
public class ShipmentController {
    private final ShipmentRepository shipmentRepository;

    public ShipmentController(ShipmentRepository shipmentRepository) {
        this.shipmentRepository = shipmentRepository;
    }

    public record ShipmentIn(@NotBlank String company,
                             @NotBlank String tracking_no,
                             @NotBlank String status,
                             @Min(1) Integer pieces) {}

    @GetMapping("/shipments")
    public List<Shipment> list() {
        return shipmentRepository.findAll().stream()
                .sorted((a, b) -> Long.compare(b.getId(), a.getId()))
                .toList();
    }

    @PostMapping("/shipments")
    public Shipment create(@RequestBody ShipmentIn in) {
        Shipment s = new Shipment();
        s.setCompany(in.company());
        s.setTrackingNo(in.tracking_no());
        s.setStatus(in.status() != null ? in.status() : "Created");
        s.setPieces(in.pieces() != null ? in.pieces() : 1);
        return shipmentRepository.save(s);
    }

    @PutMapping("/shipments/{id}")
    public ResponseEntity<?> update(@PathVariable Long id, @RequestBody ShipmentIn in) {
        Optional<Shipment> opt = shipmentRepository.findById(id);
        if (opt.isEmpty()) return ResponseEntity.notFound().build();
        Shipment s = opt.get();
        s.setCompany(in.company());
        s.setTrackingNo(in.tracking_no());
        s.setStatus(in.status());
        s.setPieces(in.pieces());
        return ResponseEntity.ok(shipmentRepository.save(s));
    }

    @DeleteMapping("/shipments/{id}")
    public ResponseEntity<?> delete(@PathVariable Long id) {
        if (!shipmentRepository.existsById(id)) return ResponseEntity.notFound().build();
        shipmentRepository.deleteById(id);
        return ResponseEntity.ok().body(java.util.Map.of("ok", true));
    }

    @GetMapping("/track/{reference}")
    public List<Shipment> track(@PathVariable("reference") String reference) {
        if (reference == null || reference.isBlank()) return java.util.List.of();
        return shipmentRepository.findTop50ByTrackingNoContainingIgnoreCaseOrderByIdDesc(reference);
    }
}


