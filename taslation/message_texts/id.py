"""Indonesian (Bahasa Indonesia) templates for `taslation.messages` (see `taslation.message_texts`): Anda, as the
window; its buttons as the window names them (Hentikan). Nouns do not change after a
number, so counts need no plural words.

Machine-translated; no native review."""

TEMPLATES: dict[str, str] = {
    "batch.reply_unusable": "balasan model tidak dapat dipakai",
    "batch.note_gave_up": "{units} unit halaman ditinggalkan setelah gagal berulang kali; unit itu diterjemahkan saat halamannya dibaca",
    "batch.note_retry_failed": "permintaan untuk {bubbles} baris gagal ({error}); dicoba lagi dalam dua bagian",
    "batch.note_retry_unusable": "permintaan untuk {bubbles} baris kembali tidak terpakai; dicoba lagi dalam dua bagian",
    "batch.note_unit_failed": "unit halaman {unit}: {error}; akan diterjemahkan saat halamannya dibaca",
    "batch.note_incomplete": ("{incomplete} dari {units} unit halaman kembali tidak lengkap; yang tidak lengkap diminta "
                              "ulang"),
    "batch.note_unit_incomplete": ("unit halaman {unit}: terjemahan tidak lengkap; bagian yang kurang diterjemahkan "
                                   "saat halamannya dibaca"),
    "viewer.gone": "TASlation tidak dapat melihat jendela penampil. Pastikan jendela terbuka dan tidak diminimalkan.",
    "viewer.no_area": "TASlation tidak dapat melihat jendela penampil. Pastikan jendela terbuka dan tidak diminimalkan.",
    "viewer.windows_only": "penangkapan jendela hanya tersedia di Windows",
    "viewer.api_failed": "TASlation tidak dapat melihat jendela penampil. Pastikan jendela terbuka dan tidak diminimalkan.",
    "viewer.window_api_failed": "TASlation tidak dapat melihat jendela penampil. Pastikan jendela terbuka dan tidak diminimalkan.",
    "viewer.empty_rect": "TASlation tidak dapat melihat jendela penampil. Pastikan jendela terbuka dan tidak diminimalkan.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Mencari balon...",
    "pipeline.stage_reading": "Membaca teks {done}/{total}...",
    "pipeline.stage_translating": "Menerjemahkan {bubbles} balon dengan {translator}...",
    "pipeline.stage_rendering": "Menggambar halaman...",
    "pipeline.no_translator": "tidak ada penerjemah yang diatur",
    "pipeline.cancelled": "dibatalkan",
    "pipeline.from_cache": "{bubbles} baris ditampilkan dari terjemahan sebelumnya.",
    "pipeline.translated": "{bubbles} baris diterjemahkan dalam {seconds:.0f} dtk.",
    "pipeline.to_review": "{review} layak dilihat (dengan Mode pembaca mati, Menu > Tinjau...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "Tidak ada halaman di penampil. Pastikan buku terbuka, atau pakai Atur area... di Menu.",
    "ollama.unreachable": "TASlation tidak dapat menjangkau program penerjemah. Tekan Terjemahkan sebentar lagi; program berjalan sendiri.",
    "ollama.model_missing": "Model terjemahan {model} belum terpasang. Jalankan install.cmd lagi untuk memasangnya.",
    "ollama.http_error": "Program penerjemah menolak ({status}). Tekan Terjemahkan untuk mencoba lagi; jika terulang, mulai ulang PC Anda.",
    "ollama.timeout": "Penerjemahan terlalu lama. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.connection_failed": "Program penerjemah berhenti menjawab. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.bad_json": "Program penerjemah memberi jawaban yang tidak dapat dipakai TASlation. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.reported_error": "Program penerjemah memberi jawaban yang tidak dapat dipakai TASlation. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.broke_off": "Program penerjemah memberi jawaban yang tidak dapat dipakai TASlation. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.bad_answer": "Program penerjemah memberi jawaban yang tidak dapat dipakai TASlation. Tekan Terjemahkan untuk mencoba lagi.",
    "ollama.not_loopback": "URL Ollama harus berupa alamat http(s) loopback (komputer ini), bukan “{url}”",
    "ollama.slow": "Program penerjemah lambat menjawab (mungkin masih memuat). Hentikan membatalkan halaman ini.",
    "ollama.no_answer": "Program penerjemah tidak menjawab selama {seconds:.0f} dtk, jadi TASlation memintanya lagi.",
    "ollama.restarting": "Program penerjemah masih tidak menjawab, jadi TASlation memulainya lagi...",
    "ollama.not_answering": ("Program penerjemah di komputer ini tidak menjawab. Mulai ulang program itu (atau mulai "
                             "ulang TASlation), lalu tekan Terjemahkan."),
    "ollama.loaded": "Penerjemah siap.",
    "ollama.loading": "Menyiapkan penerjemah...",
    "ollama.partly_on_gpu": "Hanya {percent}% penerjemah yang muat di kartu grafis, jadi penerjemahan akan lambat. Tutup program lain yang memakai kartu grafis.",
    "translator.failed": "{detail}",
    "ocr.model_missing": ("Bagian yang membaca teks Jepang tidak ada. Klik dua kali install.cmd di folder TASlation. Halaman yang sudah diterjemahkan tetap tampil."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "Pembacaan teks Jepang berjalan dalam bentuk dasar. Klik dua kali install.cmd untuk meningkatkannya.",
    "layout.classical": "Teks di atas gambar dicari dengan cara dasar. Klik dua kali install.cmd untuk menemukan lebih banyak.",
    "health.ollama_down": ("Program penerjemah tidak berjalan, jadi halaman baru tidak dapat diterjemahkan. TASlation mencoba menjalankannya di halaman berikutnya; jika pesan ini tetap ada, mulai ulang PC Anda. Halaman yang sudah diterjemahkan tetap dapat dibaca."),
    "health.ollama_not_installed": "Program penerjemah belum terpasang. Klik dua kali install.cmd di folder TASlation.",
    "health.ollama_no_answer": ("Program penerjemah tidak berjalan. Mulai ulang PC Anda, lalu buka TASlation lagi. Halaman yang sudah diterjemahkan tetap dapat dibaca."),
    "health.model_missing": "Model terjemahan {model} belum terpasang. Jalankan install.cmd lagi untuk memasangnya.",
    "health.chosen_model_missing": ("Model {model} yang dipilih di pengaturan belum terpasang di Ollama. Jalankan di "
                                    "terminal: {command}"),
    "health.ocr_missing": ("Bagian yang membaca teks Jepang tidak ada. Klik dua kali install.cmd di folder TASlation. Halaman yang sudah diterjemahkan tetap tampil."),
    "health.other_model": ("{wanted} belum terpasang di Ollama; untuk sementara menerjemahkan dengan {used}. "
                           "Jalankan install.cmd lagi untuk memasang {wanted}."),
    "health.chosen_other_model": ("{wanted} yang dipilih di pengaturan belum terpasang di Ollama; untuk sementara "
                                  "menerjemahkan dengan {used}. Untuk memasang {wanted}, jalankan di terminal: "
                                  "{command}"),
    "pipeline.no_text": "Tidak ada teks di halaman ini.",
    "rename.unreadable": "{path} tidak dapat dibaca. Pindahkan keluar dari {folder}, lalu coba lagi.",
    "rename.busy": "{path} tidak dapat dibuka sekarang. Tutup program yang menahannya, lalu coba lagi.",
    "rename.in_way": "{path} menghalangi. Pindahkan keluar dari {folder}, lalu coba lagi.",
    "rename.no_name": "Nama itu tidak menyebut buku apa pun; beri buku ini namanya sendiri.",
    "rename.same_name": "Buku ini sudah bernama {book}.",
    "store.protected": "{files} file tersimpan dilindungi: mulai sekarang hanya pengguna Windows ini yang dapat membukanya, di komputer ini.",
    "store.not_protected": "{files} file tersimpan belum dapat dilindungi: program lain sedang memakainya. TASlation akan mencoba lagi saat dimulai berikutnya.",
    "store.not_here": "{files} file tersimpan tidak dapat dibuka oleh pengguna Windows ini di komputer ini: disimpan oleh pengguna Windows lain atau di komputer lain, atau rusak. TASlation tidak pernah menimpanya: buku seperti itu dimulai dari awal, dan filenya disimpan di sebelahnya dengan nama baru. Untuk membawa terjemahan sebuah buku ke sini, ekspor terjemahan itu di tempat ia disimpan (Menu > Terjemahan tersimpan... > Ekspor (terenkripsi)...) lalu impor file tersebut di sini (Impor...).",
    "store.set_aside": "Sebuah file tersimpan dari buku ini tidak dapat dibuka oleh pengguna Windows ini di komputer ini: disimpan oleh pengguna Windows lain atau di komputer lain, atau rusak. File itu disimpan sebagai {path}, dan buku ini dimulai dari awal di sini. Untuk membawa terjemahannya ke sini, ekspor di tempat ia disimpan (Menu > Terjemahan tersimpan... > Ekspor (terenkripsi)...) lalu impor file tersebut di sini (Impor...).",
    # the translation model the target language chooses (translate/models.py, translate/plamo.py)
    "translator.model_missing": "Model terjemahan untuk bahasa ini, {name}, belum terpasang. Jalankan install.cmd lagi untuk memasangnya.",
    "translator.other_model": "Model terjemahan untuk bahasa ini, {name}, belum terpasang; untuk sementara menerjemahkan dengan {used}. Jalankan install.cmd lagi untuk memasang {name}.",
    "plamo.cannot_write": "Model yang dipilih di pengaturan tidak bisa menerjemahkan ke bahasa ini. Hapus ollama_model dari berkas pengaturan, maka TASlation memilih sendiri model yang tepat.",
}
