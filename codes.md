# Athena-Academic — Sohbet Komutları (/codes)

Sohbet kutusunda `/` ile başlayan komutlar **yapay zekânın yönlendirme kararını
beklemeden** doğrudan ilgili işleme gider. Komut, mesajın başında olmalıdır;
geri kalan metin komutun girdisi olarak kullanılır. Tarih belirtmezsen görev
**tarihsiz** oluşturulur (varsayılan bir son tarih atanmaz).

| Komut | Ne yapar | Örnek |
|-------|----------|-------|
| `/görev <metin>` | Günlük (general) görev oluşturur. Ekstra detaylar notlara yazılır. | `/görev Market alışverişi` |
| `/agörev <metin>` | Akademik görev oluşturur (alt görev üretmez). | `/agörev Lineer cebir problem seti 4` |
| `/altgörev(n) <metin>` | Akademik görev oluşturur ve `n` alt göreve böler. (Eski `/altakademik` adı hâlâ çalışır.) | `/altgörev(5) Dönem projesi` |
| `/fikir(n) <metin>` | Verilen metinden en fazla `n` fikir çıkarır. | `/fikir(3) uzun beyin fırtınası notu` |
| `/antrenman <metin>` | Tek bir tamamlanan antrenman ekler (süre + RPE). | `/antrenman 45 dk tempo koşu RPE 7` |
| `/seans <metin>` | Akademik bir görevin altına çalışma seansı ekler (@görev_adı). | `/seans 2 saat integral tekrarı @analiz` |
| `/plan <metin>` | Akademik bir hedeften görev + alt görevler üretir. | `/plan Termodinamik final hazırlığı` |
| `/aralık(n) <metin>` | Aralıklı tekrar (spaced repetition) görevi; alt görevler de aralıklı olur. | `/aralık Bölüm 3 tekrarı` |
| `/yardim` | Komut listesini gösterir. | `/yardim` |

Türkçe/İngilizce takma adlar: `/gorev` `/agorev` `/altgorev` `/aralik` `/yardım`.

## Notlar
- Komut tanınmazsa mesaj normal şekilde AI yönlendiricisine gider (hata vermez).
  Boş olmayan her girdi en az bir görev/sonuç üretir; "çıkaramadım" denmez.
- Görevleri **tamamlama, silme, not ekleme ve tarih düzenleme** işlemleri Görevler
  ve Günüm sayfalarındaki görev kartlarından yapılır (sohbet komutu değil).
- Sohbete **dosya (PDF/görüntü)** ekleyebilirsin: PDF'ler Markdown'a çevrilir,
  görüntüler vision modeliyle okunur. Eklenen materyal, oluşturulan görevin içine
  iliştirilir ve proje görevlerinde alt görev üretiminde kullanılır.
- Akademik görevlerde ilerleme (progress), notlar ve materyaller bulunur; günlük
  görevler sadeleştirilmiştir.
