# Dokumentasi Infrastruktur TI - RS Yogyakarta (SINTETIS)

Dokumen ini fiktif dan hanya berisi informasi infrastruktur TI. Tidak ada data pasien.

## Topologi Jaringan
Jalur logis dari endpoint ke server aplikasi: PC unit -> switch akses unit -> SW-DIST-01/SW-DIST-02 -> CORE-SW-01 -> RTR-CORE -> server.
Setiap switch akses terhubung ke distribution switch melalui uplink Gi0/48. Server SIMRS-APP-01, SIMRS-DB-01, DNS-01, FILE-01 dan MONITOR-01 berada di VLAN 20 dan terhubung langsung ke RTR-CORE.

## VLAN
VLAN 10 Management, VLAN 20 Server, VLAN 30 Poli (Poli 1-3), VLAN 40 Farmasi, VLAN 50 Kasir, VLAN 60 Laboratorium, VLAN 70 Penunjang/IGD (Radiologi, IGD, Rekam Medis).

## Layanan
SIMRS berjalan pada SIMRS-APP-01 port 8080, SIM-APOTEK port 8081. Database SIMRS berjalan pada SIMRS-DB-01 port 5432. DNS internal pada DNS-01 port 53 (zona simrs.internal). File server FILE-01 port 445. Monitoring pada MONITOR-01 port 9090.

## Dependensi
SIMRS bergantung pada DNS-01 (resolusi nama simrs.internal) dan SIMRS-DB-01 (database). Gangguan DNS menyebabkan aplikasi tidak dapat dibuka dengan nama host meskipun server sehat. Gangguan switch akses hanya mempengaruhi endpoint di bawah switch tersebut.

## Baseline Normal
Latency endpoint ke SIMRS-APP-01 normal 1-9 ms, packet loss 0%. Response health SIMRS 90-160 ms. CPU SIMRS-APP-01 jam kerja 38-58%, memori 58-66%. Koneksi database aktif normal di bawah 40 dari batas 100.
