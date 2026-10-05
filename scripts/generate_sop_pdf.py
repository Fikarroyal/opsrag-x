#!/usr/bin/env python
"""Generate the SYNTHETIC hospital IT SOP PDF (data/sop/hospital_it_sop.pdf).

Some SOPs have several versions (superseded / active / scheduled) so that the
version-aware retrieval (SOP effective at incident time) can be demonstrated.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sop" / "hospital_it_sop.pdf"

SOPS = {
    "SOP-001": dict(
        title="Penanganan SIMRS Tidak Dapat Diakses",
        category="application",
        tujuan="Menyediakan penanganan terstruktur ketika SIMRS atau SIM-APOTEK tidak dapat dibuka oleh pengguna.",
        indikasi="SIMRS tidak dapat dibuka, halaman error 502/503, loading tidak selesai atau timeout dari satu atau lebih unit.",
        prasyarat="Akses read-only ke monitoring, daftar perangkat terdampak, dan waktu awal gangguan.",
        investigasi=[
            "Tentukan cakupan: satu perangkat, satu unit, beberapa unit atau seluruh rumah sakit.",
            "Periksa status layanan SIMRS dan health endpoint aplikasi.",
            "Periksa resolusi DNS untuk simrs.internal.",
            "Periksa konektivitas jaringan dari perangkat terdampak dan dari perangkat pembanding di unit lain.",
            "Periksa status server aplikasi (CPU, memori) dan koneksi ke database.",
            "Korelasikan log jaringan, aplikasi dan database pada rentang 15 menit sebelum dan sesudah gangguan.",
        ],
        indikator="Health endpoint 200 dengan response normal menunjukkan aplikasi sehat. Packet loss pada endpoint terdampak menunjukkan masalah jalur jaringan. DNS SERVFAIL menunjukkan masalah DNS. Error connection timeout pada log aplikasi menunjukkan masalah database.",
        remediation=[
            "Jika layanan aplikasi berhenti, restart service SIMRS setelah persetujuan penanggung jawab.",
            "Jika penyebab berada pada jaringan, ikuti SOP-003 atau SOP-007.",
            "Jika penyebab DNS, ikuti SOP-002. Jika penyebab database, ikuti SOP-005.",
            "Catat seluruh tindakan pada tiket.",
        ],
        verifikasi="Health endpoint SIMRS mengembalikan 200 kurang dari 500 ms. Pengguna dari unit terdampak dapat login dan membuka menu utama.",
        rollback="Jika restart tidak memulihkan layanan, kembalikan aplikasi ke versi rilis sebelumnya sesuai prosedur rilis.",
        catatan="Semua tindakan perubahan dilakukan manual oleh staf IT berwenang. Sistem investigasi hanya memberi rekomendasi.",
        versions=[("1.0", "2026-01-15", "superseded", 5), ("1.1", "2026-06-01", "active", 6)],
    ),
    "SOP-002": dict(
        title="Penanganan DNS Failure",
        category="dns",
        tujuan="Memulihkan resolusi nama internal ketika DNS-01 gagal menjawab query.",
        indikasi="nslookup simrs.internal gagal, SERVFAIL atau timeout, aplikasi dapat dibuka lewat IP tetapi tidak lewat nama.",
        prasyarat="Akses ke DNS-01 dengan hak baca, salinan zone file terakhir, daftar record kritikal.",
        investigasi=[
            "Jalankan pemeriksaan DNS untuk simrs.internal dan catat hasil serta response time.",
            "Bandingkan dengan konektivitas langsung ke alamat IP server aplikasi.",
            "Periksa log DNS-01 untuk SERVFAIL, resolver hang atau antrian query.",
            "Periksa status layanan DNS dan resource DNS-01.",
            "Tentukan apakah dampak melebihi satu unit (indikasi masalah pusat).",
        ],
        indikator="DNS_QUERY_FAIL dari banyak unit bersamaan, ping ke IP normal, dan status layanan DNS degraded atau down menunjukkan kegagalan DNS.",
        remediation=[
            "Validasi zone file simrs.internal sebelum tindakan apapun.",
            "Restart layanan resolver pada DNS-01 setelah persetujuan.",
            "Jika zone korup, restore dari backup terakhir yang valid dan reload resolver.",
        ],
        verifikasi="check DNS simrs.internal berhasil kurang dari 50 ms dari beberapa unit. Health endpoint SIMRS dapat diakses menggunakan nama host.",
        rollback="Kembalikan zone file ke versi sebelum perubahan jika reload gagal.",
        catatan="Jangan mengubah record produksi tanpa persetujuan penanggung jawab jaringan.",
        versions=[("1.0", "2026-02-01", "active", 5)],
    ),
    "SOP-003": dict(
        title="Penanganan Network Connectivity",
        category="network",
        tujuan="Menangani gangguan konektivitas jaringan pada endpoint, switch akses atau jalur distribusi.",
        indikasi="Packet loss atau latency tinggi dari endpoint, sebagian komputer dalam satu unit tidak dapat mengakses aplikasi, koneksi putus-putus.",
        prasyarat="Daftar perangkat terdampak, topologi jaringan, akses baca ke counter interface switch.",
        investigasi=[
            "Tentukan cakupan dampak: satu endpoint, satu unit atau beberapa unit.",
            "Jika satu endpoint terdampak, periksa kabel, NIC, dan port switch.",
            "Jika satu unit terdampak, periksa switch akses, uplink ke distribution switch, VLAN dan gateway.",
            "Bandingkan dengan perangkat pembanding di unit lain untuk memastikan lokasi gangguan.",
            "Periksa counter interface uplink switch akses (CRC error, drop, flapping).",
            "Periksa latency dan packet loss uplink pada rentang 15 menit sebelum gangguan.",
            "Verifikasi bahwa server aplikasi dan DNS sehat untuk menyingkirkan penyebab di sisi server.",
        ],
        indikator="Beberapa endpoint pada switch yang sama mengalami packet loss bersamaan, latency uplink meningkat, interface error bertambah, sementara server dan DNS sehat dan unit lain normal.",
        remediation=[
            "Verifikasi uplink switch akses: kondisi kabel, transceiver dan port.",
            "Periksa interface error dan konfigurasi VLAN pada port uplink dan port endpoint.",
            "Ganti kabel atau transceiver uplink yang menunjukkan error setelah persetujuan.",
            "Jika perlu, restart switch akses pada jam dengan dampak minimal dan sesuai izin perubahan.",
            "Pulihkan konektivitas mengikuti prosedur dan catat waktu pemulihan.",
        ],
        verifikasi="ping gateway berhasil tanpa loss. Resolusi DNS berhasil. HTTP health check SIMRS 200. Pengguna unit terdampak dapat membuka SIMRS.",
        rollback="Kembalikan konfigurasi switch dari backup terakhir jika perubahan menyebabkan gangguan baru.",
        catatan="Jangan memindahkan port produksi tanpa izin. Dokumentasikan perubahan kabel.",
        versions=[("2.0", "2026-01-15", "superseded", 4), ("2.1", "2026-07-01", "active", 7), ("2.2", "2026-10-15", "scheduled", 7)],
    ),
    "SOP-004": dict(
        title="Penanganan Server Down",
        category="server",
        tujuan="Menangani server yang tidak dapat dijangkau atau layanan server berhenti.",
        indikasi="Server tidak merespons ping atau health check, alarm monitoring, layanan berhenti.",
        prasyarat="Akses ke dashboard monitoring, kontak penanggung jawab server, jadwal perawatan.",
        investigasi=[
            "Periksa status server dan resource (CPU, memori, disk).",
            "Periksa apakah server dapat dijangkau dari beberapa unit (pisahkan masalah jaringan).",
            "Periksa log server pada rentang sebelum gangguan.",
            "Periksa proses atau job terjadwal yang membebani server.",
        ],
        indikator="CPU atau memori di atas ambang, SLOW_RESPONSE atau HTTP_TIMEOUT dari semua unit, jaringan normal.",
        remediation=[
            "Hentikan job yang membebani setelah persetujuan.",
            "Restart service terdampak, jika perlu jadwalkan reboot server.",
            "Eskalasi ke penanggung jawab server jika hardware bermasalah.",
        ],
        verifikasi="Server merespons health check, CPU dan memori kembali ke baseline, response time normal.",
        rollback="Aktifkan kembali job yang dihentikan di luar jam sibuk.",
        catatan="Reboot server produksi hanya dengan izin tertulis.",
        versions=[("1.0", "2026-01-15", "active", 4)],
    ),
    "SOP-005": dict(
        title="Penanganan Database Connection Error",
        category="database",
        tujuan="Memulihkan koneksi aplikasi ke database SIMRS.",
        indikasi="Error database connection timeout pada aplikasi, HTTP 500, transaksi tidak tersimpan, pool koneksi habis.",
        prasyarat="Akses baca ke log database, status koneksi aktif, kontak DBA.",
        investigasi=[
            "Periksa status layanan DATABASE dan resource SIMRS-DB-01.",
            "Periksa log database untuk connection pool exhausted, lock atau slow query.",
            "Periksa log aplikasi untuk DB_CONN_TIMEOUT dan urutan waktunya.",
            "Pastikan jaringan dan DNS normal (bedakan dari masalah jaringan).",
        ],
        indikator="DB_CONN_POOL_EXHAUSTED atau slow query mendahului error aplikasi, semua unit terdampak, jaringan dan DNS normal.",
        remediation=[
            "Identifikasi dan akhiri session idle atau query bermasalah setelah persetujuan DBA.",
            "Sesuaikan batas koneksi dan pool aplikasi.",
            "Restart pool aplikasi bila diperlukan.",
        ],
        verifikasi="Layanan DATABASE running, koneksi aktif di bawah ambang, transaksi SIMRS dapat disimpan.",
        rollback="Kembalikan pengaturan pool dan batas koneksi ke nilai sebelumnya jika terjadi degradasi.",
        catatan="Jangan menghapus data. Semua tindakan pada database dilakukan oleh DBA.",
        versions=[("1.0", "2026-01-15", "active", 4)],
    ),
    "SOP-006": dict(
        title="Penanganan High Latency",
        category="server",
        tujuan="Menangani respons lambat pada aplikasi atau jaringan.",
        indikasi="Response time aplikasi di atas 3 detik, pengguna mengeluh lambat, SLOW_RESPONSE pada log.",
        prasyarat="Baseline response time, akses baca ke metrik server dan jaringan.",
        investigasi=[
            "Bedakan latency jaringan dari latency aplikasi dengan membandingkan ping dan HTTP response.",
            "Periksa CPU dan memori server aplikasi.",
            "Periksa job terjadwal atau lonjakan request.",
            "Periksa latency uplink switch jika hanya satu unit terdampak.",
        ],
        indikator="CPU tinggi dengan response time tinggi dari semua unit menunjukkan beban server. Latency tinggi hanya pada satu unit menunjukkan masalah jaringan lokal.",
        remediation=[
            "Hentikan atau jadwalkan ulang job berat setelah persetujuan.",
            "Restart proses aplikasi bila terjadi memory leak.",
            "Tambahkan kapasitas jika beban puncak berulang.",
        ],
        verifikasi="Response time SIMRS kurang dari 500 ms, CPU di bawah 70%.",
        rollback="Kembalikan penjadwalan job ke pengaturan semula bila diperlukan.",
        catatan="Catat pola jam sibuk untuk perencanaan kapasitas.",
        versions=[("1.0", "2026-01-15", "active", 4)],
    ),
    "SOP-007": dict(
        title="Penanganan Switch Failure",
        category="network",
        tujuan="Menangani switch akses atau distribusi yang mati atau interface uplink yang down.",
        indikasi="Seluruh endpoint di satu unit tidak memiliki koneksi, interface uplink down, switch tidak dapat dijangkau dari monitoring.",
        prasyarat="Akses fisik ke ruang switch, kabel dan transceiver cadangan, backup konfigurasi.",
        investigasi=[
            "Periksa status interface uplink switch akses dan port pada distribution switch.",
            "Periksa apakah switch dapat dijangkau dari monitoring.",
            "Periksa log INTERFACE_DOWN dan flapping.",
            "Pastikan server dan unit lain normal.",
        ],
        indikator="INTERFACE_DOWN pada uplink, seluruh endpoint di unit tidak terjangkau (packet loss 100%), unit lain dan server normal.",
        remediation=[
            "Periksa kabel dan transceiver uplink, ganti bila rusak setelah persetujuan.",
            "Periksa catu daya switch.",
            "Aktifkan kembali port dan pulihkan konfigurasi dari backup.",
        ],
        verifikasi="Interface uplink up, ping gateway berhasil, endpoint dapat membuka SIMRS dan SIM-APOTEK.",
        rollback="Pasang kembali kabel atau switch lama jika perangkat pengganti bermasalah.",
        catatan="Simpan konfigurasi switch sebelum perubahan fisik.",
        versions=[("1.0", "2026-01-15", "active", 4)],
    ),
    "SOP-008": dict(
        title="Penanganan Authentication Failure",
        category="authentication",
        tujuan="Menangani kegagalan login pengguna ke SIMRS ketika jaringan normal.",
        indikasi="Login SIMRS ditolak, pesan autentikasi gagal untuk banyak pengguna, internet normal.",
        prasyarat="Akses baca ke log autentikasi, daftar user terdampak.",
        investigasi=[
            "Pastikan jaringan dan health endpoint SIMRS normal.",
            "Periksa log AUTH_FAILURE untuk pola waktu dan sumber.",
            "Periksa sinkronisasi waktu server dan layanan direktori.",
        ],
        indikator="AUTH_FAILURE meningkat dari banyak user dengan health endpoint normal menunjukkan masalah layanan autentikasi.",
        remediation=[
            "Sinkronkan waktu server autentikasi setelah persetujuan.",
            "Restart layanan autentikasi bila perlu.",
            "Reset cache token dan verifikasi akun layanan.",
        ],
        verifikasi="Pengguna dapat login, AUTH_FAILURE kembali ke baseline.",
        rollback="Kembalikan konfigurasi autentikasi ke versi sebelumnya bila login semakin gagal.",
        catatan="Jangan membagikan atau mereset kredensial pengguna tanpa verifikasi identitas.",
        versions=[("1.0", "2026-01-15", "active", 3)],
    ),
}


def build() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=14)
    h2 = ParagraphStyle("h2", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=12)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="SOP TI RS Yogyakarta (SINTETIS)",
        author="OpsRAG-X synthetic data",
    )
    story = [
        Paragraph("Kumpulan SOP Infrastruktur TI - RS Yogyakarta", h1),
        Paragraph("Dokumen sintetis untuk OpsRAG-X. Tidak berisi data pasien.", body),
        PageBreak(),
    ]
    for code, s in SOPS.items():
        for version, eff, status, n_steps in s["versions"]:
            story.append(Paragraph(f"{code} | v{version} | Berlaku: {eff} | Status: {status} | Judul: {s['title']}", h1))
            story.append(Paragraph(f"Kode SOP: {code}. Versi: {version}. Tanggal berlaku: {eff}. Kategori: {s['category']}.", body))
            for label, key in [("Tujuan", "tujuan"), ("Indikasi", "indikasi"), ("Prasyarat", "prasyarat")]:
                story += [Paragraph(f"{label}:", h2), Paragraph(s[key], body)]
            story.append(Paragraph("Langkah Investigasi:", h2))
            for i, step in enumerate(s["investigasi"][:n_steps], start=1):
                story.append(Paragraph(f"{i}. {step}", body))
            story += [Paragraph("Indikator Evidence:", h2), Paragraph(s["indikator"], body), Paragraph("Langkah Remediation:", h2)]
            for i, step in enumerate(s["remediation"], start=1):
                story.append(Paragraph(f"{i}. {step}", body))
            for label, key in [("Verifikasi", "verifikasi"), ("Rollback", "rollback"), ("Catatan", "catatan")]:
                story += [Paragraph(f"{label}:", h2), Paragraph(s[key], body)]
            if status == "scheduled":
                story.append(Paragraph("Catatan versi: versi ini belum berlaku sebelum tanggal berlaku di atas.", body))
            story.append(PageBreak())
    doc.build(story)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
