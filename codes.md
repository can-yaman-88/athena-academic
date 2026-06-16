# Jarvis-Academic — Sohbet Komutları (/codes)

Sohbet kutusunda `/` ile başlayan komutlar **yapay zekânın yönlendirme kararını
beklemeden** doğrudan ilgili işleme gider. Komut, mesajın başında olmalıdır;
geri kalan metin komutun girdisi olarak kullanılır.

| Komut | Ne yapar | Örnek |
|-------|----------|-------|
| `/akademik <görev>` | Akademik görev oluşturur; alt türü (proje/ödev/seans) AI seçer. | `/akademik Termodinamik vize çalışması` |
| `/proje <görev>` | Akademik **PROJE** görevi. Yönerge PDF'i ekleyebilirsin; AI alt görevler üretir. | `/proje Derin öğrenme dönem projesi` (+PDF) |
| `/odev <görev>` | Akademik **ÖDEV** görevi. | `/odev Lineer cebir problem seti 4` |
| `/seans <görev>` | Akademik **ÇALIŞMA SEANSI** görevi. | `/seans 2 saat integral tekrarı` |
| `/gunluk <görev>` | Günlük (general) görev. | `/gunluk Market alışverişi` |
| `/duzenle <tarif>` | Mevcut görevi düzenler. Tarih verilmezse **bugünkü**, yoksa **en yakın gelecekteki** görev. | `/duzenle koşuyu 1.5 saate çıkar` |
| `/complete [tarih] <ad>` | Görevi tamamlar. Ad tam eşleşmezse **en benzer** görev tamamlanır. | `/complete 2026-06-20 lineer cebir` |
| `/sil [tarih] <ad>` | Görevi siler (tam eşleşme yoksa en benzer). | `/sil market` |
| `/ertele <ad> <tarih>` | Görevin son tarihini değiştirir. | `/ertele proje 2026-07-01` |
| `/antrenman <metin>` | Tek antrenman ekler (süre + RPE). | `/antrenman 45 dk tempo koşu RPE 7` |
| `/plan` (+ekli .md/.json ya da metin) | Çoklu gün antrenman planını içe aktarır. | `/plan` + aylık plan .md dosyası |
| `/not <ipucu>: <metin>` | İlgili göreve not ekler. | `/not termodinamik: bugün 2 saat çok zorlandım` |
| `/yardim` | Bu komut listesini gösterir. | `/yardim` |

İngilizce takma adlar da kabul edilir: `/academic` `/daily` `/edit` `/workout`
`/note` `/help`.

## Notlar
- Komut tanınmazsa mesaj normal şekilde AI yönlendiricisine gider (hata vermez).
- Sohbete **dosya (PDF/görüntü)** ekleyebilirsin: PDF'ler istisnasız Markdown'a
  çevrilir, görüntüler vision modeliyle okunur. Eklenen materyal, oluşturulan
  görevin içine iliştirilir ve proje görevlerinde alt görev üretiminde kullanılır.
- Akademik görevlerde ilerleme (progress), notlar ve materyaller bulunur; günlük
  görevler sadeleştirilmiştir.
