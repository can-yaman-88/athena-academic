# Athena-Academic

Otonom, ajan tabanlı (agentic) bir akademik asistan sistemi. PDF ders materyallerini
**tam bir boru hattıyla** işler (OCR/Markdown → LaTeX ders notu → derlenmiş PDF →
sınav → Anki flashcard) ve notları bilgi tabanına ekler; görevlerini, günlüklerini (journal)
ve antrenmanlarını yönetir; fiziksel yorgunluğuna göre bilişsel iş yükünü dengeler; API
maliyetini iki ayrı sayaçta (PDF vs. ajan) izler. Tüm LLM erişimi **OpenRouter** üzerinden yapılır;
yerelde yalnızca ChromaDB gömme modeli çalışır.

Arayüz beş sayfadan oluşur:
- **Günüm** — solda günün görevleri/son tarihleri ve bilişsel kapasite, sağda ajan sohbeti
  (dosya ekleme + `/` komutları ile).
- **PDF Otomasyonu** — solda geçmiş PDF'ler, ortada (üst) API maliyet/kullanım analizleri +
  (alt) PDF yükleme, altta tam genişlikte **canlı sistem logları** (Notion tarzı
  ortadan açılan büyütme penceresiyle).
- **Görevler** — **Akademik** (proje/ödev/seans alt türleri, ilerleme, alt görevler,
  notlar, materyaller, **ham dosya ekleri**) ve **Günlük** görevler için tam CRUD.
- **Antrenman** — planlı/tamamlanan antrenmanlar, TrainingPeaks tarzı opsiyonel metrikler
  (mesafe/tempo/hız/nabız), **JSON/CSV/.FIT** veri içe aktarma, **Runalyze** entegrasyonu ve çoklu-gün plan içe aktarma.
  Antrenmanlar yalnızca **tamamlandığında** bilişsel yüke eklenir.
- **Fikirler (Ideas)** — Serbest biçimli notların, fikirlerin ve dosyaların kaydedilebildiği, yapay zeka işlemesi gerektirmeyen esnek çalışma alanı.

### Öne çıkan yetenekler
- **Sohbetten görev oluştur/düzenle**: tarih verilmezse bugünkü, yoksa en yakın gelecekteki
  görev düzenlenir. Eksik bilgi hata vermez; mantıklı varsayılanlar uygulanır.
- **Otomatik Alt Görev Üretimi**: LLM kullanılarak bir ana göreve (veya plana) ait alt görevler `/altgörev`, `/altakademik` ve `/plan` komutlarıyla otomatik olarak üretilip veritabanına eklenir.
- **`/` komutları** (deterministik yönlendirme): `/görev`, `/agörev`, `/altgörev`, `/altakademik`, `/fikir`, `/antrenman`, `/seans`, `/plan`, `/aralık`, `/yardim`. Görev
  yönetimi komutları ad tam eşleşmezse **en benzer** görevi hedefler. Tümü [`codes.md`](codes.md)'de.
- **Sohbete dosya ekleme**: PDF → her zaman Markdown, görüntü → vision modeli. Eklenen
  materyal göreve iliştirilir ve proje görevlerinde **AI alt görev üretiminde** kullanılır.
- **Notlar + analiz**: göreve not ekle; "Notları analiz et" ile yüksek kapasiteli model
  notlardan metrik çıkarır — çalışma zorluğunu **o güne ait bilişsel yüke** ekler, başka
  görevlerdeki ilerlemeyi ilgili göreve işler.
- **Günlükler ve AI Analizi (Journal)**: Günlük formatında alınan notlar saklanır ve `ai-analyze` uç noktasıyla yüksek kapasiteli AI modeli tarafından analiz edilerek yapısal ögelere (JournalItem) dönüştürülür.
- **Runalyze Entegrasyonu**: Antrenman verilerini otomatik olarak veya manuel tetiklemeyle Runalyze API üzerinden arka planda senkronize edip sisteme işler.
- **Çoklu-gün antrenman planı**: bir aylık planı metin/`.md`/`.json` olarak yapıştır/yükle,
  AI tek tek antrenmana çevirip takvime ekler.

---

## İçindekiler

- [Mimari](#mimari)
- [Teknoloji Yığını](#teknoloji-yığını)
- [Önkoşullar](#önkoşullar)
- [Hızlı Başlangıç (Docker — önerilen)](#hızlı-başlangıç-docker--önerilen)
- [Yerel Geliştirme (Docker'sız)](#yerel-geliştirme-dockersız)
- [Yapılandırma (Ortam Değişkenleri)](#yapılandırma-ortam-değişkenleri)
- [API Uç Noktaları](#api-uç-noktaları)
- [Veri ve Kalıcılık](#veri-ve-kalıcılık)
- [PDF → LaTeX Motoru](#pdf--latex-motoru)
- [Proje Yapısı](#proje-yapısı)
- [Sorun Giderme](#sorun-giderme)

---

## Mimari

Sistem birbirine geçen beş katmandan oluşur:

1. **Veri katmanı** — Async SQLite (görevler, antrenmanlar, pdf işleri, fikirler, günlükler) +
   ChromaDB (yerel vektör deposu, belge gömme/sorgulama).
2. **Ajan kontrol düzlemi** — LangGraph durum makinesi: bir yönlendirici (router)
   düğümü gelen mesajı sınıflandırır (sohbet / PDF / görev), uygun düğüme yönlendirir.
   Görev düğümü serbest metinden görev alanlarını çıkarıp gerçekten kalıcılaştırır.
3. **Ajan araçları** — bilişsel yük dengeleyici ve "hardcore" Sokratik öğretmen modu
   (`@tool` ile LangGraph'a bağlanabilir).
4. **PDF motoru** — `tools/pdf_engine/automation/` altına gömülü (vendored),
   tamamen süreç-içi asenkron motor: `pymupdf4llm` ile metin çıkarımı (taranmış
   PDF'lerde görsel/OCR'a düşer) → OpenRouter ile LaTeX ders notu → `pdflatex/lualatex`
   ile derleme (deterministik + LLM self-correction) → sınav + Anki flashcard; notlar
   ChromaDB'ye eklenir. Kaynak depodaki senkronizasyon/watcher/TUI parçaları çıkarıldı.
5. **Ürün yüzeyi** — FastAPI backend + Vite/React/Tailwind koyu tema **5 sayfalı** SPA
   (react-router) + Docker/Compose altyapısı. Canlı log akışı ve iki kanallı maliyet
   takibi dahil.

```
Tarayıcı (React SPA :8088)  ──HTTP/SSE──>  FastAPI (:8888)
                                              ├── LangGraph ajanı ──> OpenRouter
                                              ├── SQLiteManager  ──> data/athena.db
                                              ├── ChromaManager  ──> data/chroma/
                                              └── PDF motoru (arka plan görevi)
```

## Teknoloji Yığını

| Katman    | Teknoloji                                                        |
|-----------|------------------------------------------------------------------|
| Backend   | Python 3.12+, FastAPI, Uvicorn, Pydantic v2                      |
| Ajan      | LangGraph, LangChain, langchain-openai (OpenRouter ağ geçidi)   |
| Veri      | aiosqlite (WAL), ChromaDB (all-MiniLM-L6-v2, CPU)               |
| Frontend  | Vite + React + TypeScript + Tailwind CSS v3                     |
| Dağıtım   | Docker, Docker Compose, nginx (statik servis)                  |

---

## Önkoşullar

**Docker yolu için (önerilen):**
- Docker + Docker Compose
- Bir **OpenRouter API anahtarı** — https://openrouter.ai/keys

**Yerel geliştirme yolu için (ek olarak):**
- Python 3.12+ (depo `.venv` ile Python 3.14 kullanıyor)
- Node.js 20+ ve npm
- PDF işleme gerçekten kullanılacaksa: `texlive-latex-base` + `poppler-utils`

---

## Hızlı Başlangıç (Docker — önerilen)

### 1. OpenRouter anahtarını ayarla

LLM özellikleri (`/chat`, AI analizi vb.) için bir anahtar gerekir. Anahtar olmadan da sistem ayağa
kalkar; yalnızca sohbet `503` döner, geri kalan her şey (dashboard, görevler, antrenman,
fikirler, PDF yükleme vb.) çalışır.

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Kalıcı olması için proje kökünde bir `.env` dosyası oluşturabilirsin (Compose otomatik
okur):

```bash
# .env
OPENROUTER_API_KEY=sk-or-...
RUNALYZE_TOKEN=YOUR_RUNALYZE_TOKEN  # Runalyze entegrasyonu için (opsiyonel)
```

### 2. Derle ve başlat

```bash
docker compose up --build
```

Bu iki servisi ayağa kaldırır (portlar `docker-compose.yml`'de tanımlı):
- **`api_service`** → http://localhost:8888 (FastAPI; LaTeX + poppler içeren backend imajı)
- **`frontend_service`** → http://localhost:8088 (nginx ile servis edilen React SPA)

### 3. Aç ve kullan

Tarayıcıda **http://localhost:8088** adresine git ve sayfalar arasında gezin:
- **Günüm** — günün görevleri/son tarihleri + bilişsel kapasite, yanında ajan sohbeti.
- **PDF Otomasyonu** — geçmiş PDF'ler, API maliyet analizleri, PDF yükleme, canlı loglar.
- **Görevler** — akademik & günlük görevler için ekle/düzenle/sil, notlar, materyaller.
- **Antrenman** — planlı/tamamlanan antrenmanlar, metrikler, Runalyze senkronizasyonu.
- **Fikirler** — Serbest metin, materyal ve dosya yükleme ile fikir kaydı.

### 4. Sağlık kontrolü

```bash
curl http://localhost:8888/health
# {"status":"ok","graph_ready":true}   # graph_ready, anahtar varsa true olur
```

### Durdurma

```bash
docker compose down          # konteynerleri durdur (veri korunur — ./data bind mount)
docker compose down -v       # + adlandırılmış volume'ları sil (varsa)
```

---

## Yerel Geliştirme (Docker'sız)

### Backend

```bash
# Sanal ortam (depoda zaten .venv var; yeniden oluşturmak istersen):
python3 -m venv .venv
source .venv/bin/activate.fish     # fish kabuğu için; bash'te: source .venv/bin/activate

pip install -r requirements.txt

export OPENROUTER_API_KEY="sk-or-..."     # opsiyonel; yoksa /chat 503 döner
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Backend artık http://localhost:8000 üzerinde. İlk açılışta ChromaDB gömme modeli
(`all-MiniLM-L6-v2`) indirilir — ilk başlatma biraz uzun sürebilir.

### Frontend

```bash
cd frontend
npm install
# API adresini bildir (varsayılan zaten http://localhost:8000):
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev        # Vite dev sunucusu http://localhost:3000
```

> Not: `cors_origins` varsayılanı `http://localhost:3000`. Frontend'i başka bir
> portta çalıştırırsan backend'te `CORS_ORIGINS` ortam değişkenini güncelle.

---

## Yapılandırma (Ortam Değişkenleri)

Tüm ayarlar `config.py` içindeki tek, değişmez (frozen) `Settings` nesnesinde tutulur.
Çoğu ayarın makul yerel varsayılanı vardır; ortamdan okunanlar şunlar:

| Değişken              | Varsayılan                  | Açıklama                                                                 |
|-----------------------|-----------------------------|--------------------------------------------------------------------------|
| `OPENROUTER_API_KEY`  | _(yok)_                     | OpenRouter anahtarı. Yoksa `/chat` devre dışı (503), gerisi çalışır.    |
| `CORS_ORIGINS`        | `http://localhost:3000`     | Virgülle ayrılmış izinli kaynaklar (origins).                           |
| `RUNALYZE_TOKEN`      | _(yok)_                     | Runalyze'dan verileri çekmek için kişisel erişim belirteci.             |

`config.py` içinden ayarlanabilen diğer önemli değerler (kod düzenlemesi gerekir):

- **Ajan modelleri** (OpenRouter slug'ları): `router_model` = `google/gemini-3.5-flash`, vb.
- **PDF motoru modelleri**: `pdf_transcriber_model`, `pdf_exam_model`, vb.
- **Görev varsayılanları**: `default_discipline="General"`, vb.
- **Runalyze Senkronizasyonu**: `runalyze_sync_interval_min`, `runalyze_sync_lookback_days` gibi ayarlar.

---

## API Uç Noktaları

| Metot  | Yol                              | Açıklama                                                                 |
|--------|----------------------------------|--------------------------------------------------------------------------|
| GET    | `/health`                        | Canlılık kontrolü; `graph_ready` ajanın hazır olup olmadığını döner.    |
| POST   | `/chat`                          | `{ "message", "attachment_ids"? }` → SSE akışı. Anahtar yoksa 503.      |
| POST   | `/chat/upload`                   | Sohbet eki (PDF/görüntü/.md/.json) → Markdown'a çevirip materyal döner. |
| POST   | `/upload`                        | `multipart/form-data`: `file` (PDF) + opsiyonel `instructions`. Arka planda tam pipeline. |
| POST   | `/tasks/{id}/notes`              | Göreve not ekle (PATCH/DELETE ile düzenle/sil).                        |
| GET/POST | `/tasks`                       | Görevleri listele / oluştur.                                            |
| PATCH/DELETE | `/tasks/{id}`              | Görevi güncelle / sil. `POST /tasks/{id}/complete` tamamlar.            |
| POST   | `/notes/analyze`                 | Tüm notları analiz et → bilişsel yük + ilerleme metrikleri uygula.     |
| GET/POST | `/workouts`                    | Antrenmanları listele / kaydet (status + opsiyonel metriklerle).        |
| POST   | `/workouts/sync/runalyze`        | Runalyze'dan son aktiviteleri manuel çekip antrenman olarak kaydeder.   |
| GET/POST | `/ideas`                       | Serbest formatlı fikirleri listele / oluştur. PATCH/DELETE ile düzenle/sil. |
| POST   | `/ideas/{id}/files`              | Fikre ham dosya ekle.                                                   |
| GET/POST | `/journals`                    | Günlükleri listele / oluştur. DELETE ile sil.                           |
| POST   | `/journals/ai-analyze`           | Günlükleri AI ile analiz edip görev/bilgi maddelerine (JournalItem) dönüştür. |
| GET/POST | `/daily_notes`                 | Günlük notları listele / kaydet.                                        |
| GET    | `/pdf_jobs`                      | Geçmiş PDF işleri (durum, maliyet, çıktılar).                          |
| GET    | `/usage`                         | İki kanallı maliyet/kullanım anlık görüntüsü (`pdf` vs `agent`).        |
| GET    | `/logs/stream`                   | Canlı sistem logları (SSE).                                             |

### Hızlı örnekler

```bash
# Dashboard verisi
curl http://localhost:8000/dashboard_data | jq

# Runalyze Senkronizasyonunu Tetikle
curl -X POST http://localhost:8000/workouts/sync/runalyze | jq

# PDF yükle (tam pipeline arka planda çalışır)
curl -X POST http://localhost:8000/upload \
  -F "file=@ders_notu.pdf" -F "instructions=Özet ve formüllere odaklan"
```

---

## Veri ve Kalıcılık

Tüm kalıcı durum `./data/` altında tutulur ve Docker'da `./data:/app/data` bind mount
ile host'a yansıtılır — yani `docker compose down` sonrası veriler kaybolmaz.

```
data/
├── athena.db        # SQLite: görevler, antrenmanlar, pdf işleri, fikirler (WAL modu)
├── chroma/          # ChromaDB kalıcı vektör deposu
├── uploads/         # /upload ile yüklenen ham PDF'ler
├── usage.csv        # Kalıcı API kullanım/maliyet geçmişi
├── pdf/             # Motor çıktıları: output/ (notlar), exams/, flashcards/, temp/
├── task_files/      # Görevlere eklenen ham dosyalar
└── idea_files/      # Fikirlere eklenen ham dosyalar
```

---

## PDF → LaTeX Motoru

PDF motoru artık **tamamen süreç-içi** (in-process) çalışır; ayrı bir komut/servis
gerektirmez. Kaynak,
[PDF-OCR-MD-LaTeX-PDF-Lecture-Automation](https://github.com/can-yaman-88/PDF-OCR-MD-LaTeX-PDF-Lecture-Automation)
deposundan `tools/pdf_engine/automation/` altına gömülmüştür.

Boru hattı:
1. **Metin çıkarımı** — `pymupdf4llm` ile metin katmanı Markdown'a çevrilir; metin yetersizse OCR.
2. **Transkripsiyon** — OpenRouter modeliyle temiz bir LaTeX ders notu üretilir.
3. **Derleme** — `lualatex/xelatex/pdflatex` ile derlenir; hata olursa önce deterministik düzeltmeler, sonra LLM self-correction uygulanır.
4. **Bilgi tabanı** — notlar ChromaDB'ye parçalanarak eklenir.
5. **Sınav + Flashcard** — aynı notlardan sınav PDF'i ve Anki kartları üretilir.

---

## Proje Yapısı

```
Athena/
├── app.py                      # FastAPI uygulaması (lifespan, CORS, uç noktalar)
├── config.py                   # Tek değişmez Settings nesnesi
├── requirements.txt
├── Dockerfile.worker           # Backend imajı (LaTeX + poppler + Python)
├── docker-compose.yml          # api_service + frontend_service + volume'lar
├── .dockerignore
├── codes.md                    # Sohbet `/` komutlarının tam listesi
├── core/
│   ├── schemas.py              # Görev, Antrenman, Fikir, Günlük vb. şemalar
│   ├── state.py                # AthenaState
│   ├── graph.py                # LangGraph: router / chat / pdf / task / workout
│   ├── commands.py             # Slash komutları
│   ├── journal_analyzer.py     # Günlükleri ayrıştırıp JournalItem üreten araç
│   └── ...                     
├── db/
│   ├── sqlite_manager.py       # Async CRUD işlemleri
│   └── chroma_manager.py       # ChromaDB vektör araması
├── tools/
│   ├── agentic_tools/
│   ├── workout_import.py       # JSON/CSV/.FIT dosya içe aktarıcı
│   └── pdf_engine/             # Süreç içi çalışan PDF boru hattı
└── frontend/                   # Vite + React + TS + Tailwind SPA
    ├── src/pages/              # HomePage, PdfPage, ManagePage, WorkoutsPage, IdeasPage
    ├── src/components/         # Arayüz bileşenleri
    └── ...
```

---

## Sorun Giderme

**`/chat` 503 dönüyor / `graph_ready: false`**
OpenRouter anahtarı ayarlı değil. `OPENROUTER_API_KEY` ortam değişkenini (veya `.env`
dosyasını) ayarlayıp servisi yeniden başlat.

**Runalyze senkronizasyonu çalışmıyor / 400 Hatası veriyor**
`.env` dosyanızda veya sistem değişkenlerinde `RUNALYZE_TOKEN` değerinin ayarlı olduğundan emin olun. 

**İlk başlatma yavaş**
ChromaDB ilk kullanımda `all-MiniLM-L6-v2` gömme modelini indirir. Bu tek seferliktir.

**PDF yükleniyor ama çıktı üretilmiyor**
OpenRouter API anahtarı yoksa transkripsiyon başarısız olur ve iş "failed" işaretlenir. Derleme için TeX zinciri gereklidir. Ne olduğunu "PDF Otomasyonu" sayfasındaki canlı loglardan izleyebilirsiniz.
