# Athena-Academic

Otonom, ajan tabanlı (agentic) bir akademik asistan sistemi. PDF ders materyallerini
**tam bir boru hattıyla** işler (OCR/Markdown → LaTeX ders notu → derlenmiş PDF →
sınav → Anki flashcard) ve notları bilgi tabanına ekler; görevlerini ve antrenmanlarını
yönetir; fiziksel yorgunluğuna göre bilişsel iş yükünü dengeler; API maliyetini iki ayrı
sayaçta (PDF vs. ajan) izler. Tüm LLM erişimi **OpenRouter** üzerinden yapılır;
yerelde yalnızca ChromaDB gömme modeli çalışır.

Arayüz dört sayfadan oluşur:
- **Günüm** — solda günün görevleri/son tarihleri ve bilişsel kapasite, sağda ajan sohbeti
  (dosya ekleme + `/` komutları ile).
- **PDF Otomasyonu** — solda geçmiş PDF'ler, ortada (üst) API maliyet/kullanım analizleri +
  (alt) PDF yükleme, altta tam genişlikte **canlı sistem logları** (Notion tarzı
  ortadan açılan büyütme penceresiyle).
- **Görevler** — **Akademik** (proje/ödev/seans alt türleri, ilerleme, alt görevler,
  notlar, materyaller, **ham dosya ekleri**) ve **Günlük** görevler için tam CRUD.
- **Antrenman** — planlı/tamamlanan antrenmanlar, TrainingPeaks tarzı opsiyonel metrikler
  (mesafe/tempo/hız/nabız), **JSON/CSV/.FIT** veri içe aktarma ve çoklu-gün plan içe aktarma.
  Antrenmanlar yalnızca **tamamlandığında** bilişsel yüke eklenir.

### Öne çıkan yetenekler
- **Sohbetten görev oluştur/düzenle**: tarih verilmezse bugünkü, yoksa en yakın gelecekteki
  görev düzenlenir. Eksik bilgi hata vermez; mantıklı varsayılanlar uygulanır.
- **`/` komutları** (deterministik yönlendirme): `/akademik`, `/proje`, `/duzenle`,
  `/complete`, `/sil`, `/ertele`, `/antrenman`, `/plan`, `/not`, `/yardim` … Görev
  yönetimi komutları ad tam eşleşmezse **en benzer** görevi hedefler. Tümü [`codes.md`](codes.md)'de.
- **Sohbete dosya ekleme**: PDF → her zaman Markdown, görüntü → vision modeli. Eklenen
  materyal göreve iliştirilir ve proje görevlerinde **AI alt görev üretiminde** kullanılır.
- **Notlar + analiz**: göreve not ekle; "Notları analiz et" ile yüksek kapasiteli model
  notlardan metrik çıkarır — çalışma zorluğunu **o güne ait bilişsel yüke** ekler, başka
  görevlerdeki ilerlemeyi ilgili göreve işler.
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

1. **Veri katmanı** — Async SQLite (görevler, antrenmanlar, PDF işleri) +
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
5. **Ürün yüzeyi** — FastAPI backend + Vite/React/Tailwind koyu tema **3 sayfalı** SPA
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

LLM özellikleri (`/chat`) için bir anahtar gerekir. Anahtar olmadan da sistem ayağa
kalkar; yalnızca sohbet `503` döner, geri kalan her şey (dashboard, görevler, antrenman,
PDF yükleme) çalışır.

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Kalıcı olması için proje kökünde bir `.env` dosyası oluşturabilirsin (Compose otomatik
okur):

```bash
# .env
OPENROUTER_API_KEY=sk-or-...
```

### 2. Derle ve başlat

```bash
docker compose up --build
```

Bu iki servisi ayağa kaldırır (portlar `docker-compose.yml`'de tanımlı):
- **`api_service`** → http://localhost:8888 (FastAPI; LaTeX + poppler içeren backend imajı)
- **`frontend_service`** → http://localhost:8088 (nginx ile servis edilen React SPA)

### 3. Aç ve kullan

Tarayıcıda **http://localhost:8088** adresine git ve dört sayfa arasında gezin:
- **Günüm** — günün görevleri/son tarihleri + bilişsel kapasite, yanında ajan sohbeti.
- **PDF Otomasyonu** — geçmiş PDF'ler, API maliyet analizleri, PDF yükleme, canlı loglar.
- **Görevler** — akademik & günlük görevler için ekle/düzenle/sil, notlar, materyaller.
- **Antrenman** — planlı/tamamlanan antrenmanlar, metrikler, JSON/CSV/.FIT içe aktarma.

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

`config.py` içinden ayarlanabilen diğer önemli değerler (kod düzenlemesi gerekir):

- **Ajan modelleri** (OpenRouter slug'ları): `router_model` = `google/gemini-3.5-flash`,
  `chat_model` = `google/gemini-3.1-pro-preview`. Kayıtlı seçenekler: `haiku`, `opus`,
  `gemini-flash`, `gemini-pro`.
- **PDF motoru modelleri**: `pdf_transcriber_model` (vision gerekli, varsayılan
  `gemini-3.1-pro-preview`), `pdf_exam_model`, `pdf_flashcard_model`, `pdf_validator_model`;
  LaTeX motorları/zaman aşımı; `pdf_generate_exam` / `pdf_generate_flashcards` açma-kapama.
- **Görev varsayılanları** (eksik bilgi hata vermesin diye): `default_discipline="General"`,
  `default_estimated_hours=1.0`, `default_deadline_hour=23` / `default_deadline_minute=59`.
- **Maliyet fiyatlandırması**: `model_pricing` (slug → 1M token başına prompt/completion USD),
  `usage_csv_path` (kalıcı kullanım geçmişi).

---

## API Uç Noktaları

| Metot  | Yol                              | Açıklama                                                                 |
|--------|----------------------------------|--------------------------------------------------------------------------|
| GET    | `/health`                        | Canlılık kontrolü; `graph_ready` ajanın hazır olup olmadığını döner.    |
| POST   | `/chat`                          | `{ "message", "attachment_ids"? }` → SSE akışı. Anahtar yoksa 503.      |
| POST   | `/chat/upload`                   | Sohbet eki (PDF/görüntü/.md/.json) → Markdown'a çevirip materyal döner. |
| POST   | `/upload`                        | `multipart/form-data`: `file` (PDF) + opsiyonel `instructions`. Arka planda tam pipeline. |
| POST   | `/tasks/{id}/notes`              | Göreve not ekle (PATCH/DELETE ile düzenle/sil).                        |
| POST   | `/tasks/{id}/materials`          | Göreve materyal (bağlantı/dosya) ekle.                                 |
| GET    | `/tasks/{id}/subtasks`           | Görevin alt görevlerini listele.                                       |
| POST   | `/tasks/{id}/generate_subtasks`  | Yüksek kapasiteli modelle alt görev üret.                              |
| POST   | `/notes/analyze`                 | Tüm notları analiz et → bilişsel yük + ilerleme metrikleri uygula.     |
| GET    | `/dashboard_data`                | Görevler, bekleyen sayısı, güncel bilişsel yük.                         |
| GET/POST | `/tasks`                       | Görevleri listele / oluştur.                                            |
| PATCH/DELETE | `/tasks/{id}`              | Görevi güncelle / sil. `POST /tasks/{id}/complete` tamamlar.            |
| GET/POST | `/workouts`                    | Antrenmanları listele / kaydet (status + opsiyonel metriklerle).        |
| PATCH/DELETE | `/workouts/{id}`           | Antrenmanı güncelle / sil.                                              |
| POST   | `/workouts/{id}/complete`        | Planlı antrenmanı tamamla (artık bilişsel yüke sayılır).               |
| POST   | `/workouts/upload`               | JSON/CSV/.FIT veri dosyasını tamamlanmış antrenmanlara dönüştürür.      |
| POST   | `/tasks/{id}/files`              | Göreve **ham dosya** ekle (işlenmez, yapay zekâya gönderilmez).        |
| GET    | `/tasks/{id}/materials/{mid}/download` | Göreve ekli dosyayı indir.                                       |
| GET    | `/pdf_jobs`                      | Geçmiş PDF işleri (durum, maliyet, çıktılar).                          |
| GET    | `/pdf_jobs/{id}/artifact/{name}` | Bir çıktıyı (notes/exam/flashcard) indir.                              |
| GET    | `/usage`                         | İki kanallı maliyet/kullanım anlık görüntüsü (`pdf` vs `agent`).        |
| GET    | `/logs/stream`                   | Canlı sistem logları (SSE).                                             |

### Hızlı örnekler

```bash
# Dashboard verisi
curl http://localhost:8000/dashboard_data | jq

# Görev oluştur
curl -X POST http://localhost:8000/tasks -H "Content-Type: application/json" \
  -d '{"title":"3. bölümü oku","deadline":"2026-06-20T09:00","discipline":"Math","estimated_hours":2}' | jq

# Antrenman kaydet (RPE 9, 60 dk → ağır yük; 12 saat bilişsel blok)
curl -X POST http://localhost:8000/workouts -H "Content-Type: application/json" \
  -d '{"duration_minutes":60,"rpe_score":9}' | jq

# PDF yükle (tam pipeline arka planda çalışır)
curl -X POST http://localhost:8000/upload \
  -F "file=@ders_notu.pdf" -F "instructions=Özet ve formüllere odaklan"

# Maliyet sayaçları + canlı loglar
curl http://localhost:8000/usage | jq
curl -N http://localhost:8000/logs/stream
```

---

## Veri ve Kalıcılık

Tüm kalıcı durum `./data/` altında tutulur ve Docker'da `./data:/app/data` bind mount
ile host'a yansıtılır — yani `docker compose down` sonrası veriler kaybolmaz.

```
data/
├── athena.db        # SQLite: görevler, antrenmanlar, PDF işleri (WAL modu)
├── chroma/          # ChromaDB kalıcı vektör deposu
├── uploads/         # /upload ile yüklenen ham PDF'ler
├── usage.csv        # Kalıcı API kullanım/maliyet geçmişi
└── pdf/             # Motor çıktıları: output/ (notlar), exams/, flashcards/, temp/
```

Sıfırlamak istersen `data/` dizinini silmen yeterli (konteynerler durmuşken).

---

## PDF → LaTeX Motoru

PDF motoru artık **tamamen süreç-içi** (in-process) çalışır; ayrı bir komut/servis
gerektirmez. Kaynak,
[PDF-OCR-MD-LaTeX-PDF-Lecture-Automation](https://github.com/can-yaman-88/PDF-OCR-MD-LaTeX-PDF-Lecture-Automation)
deposundan `tools/pdf_engine/automation/` altına gömülmüştür (senkronizasyon, watcher
ve TUI parçaları çıkarıldı). Boru hattı:

1. **Metin çıkarımı** — `pymupdf4llm` ile metin katmanı Markdown'a çevrilir; metin yetersizse
   sayfalar görsele çevrilip (`pdf2image`) vision modeline gönderilir (OCR).
2. **Transkripsiyon** — OpenRouter modeliyle temiz bir LaTeX ders notu üretilir.
3. **Derleme** — `lualatex/xelatex/pdflatex` ile derlenir; hata olursa önce deterministik
   düzeltmeler, sonra LLM self-correction uygulanır (döngü korumalı).
4. **Bilgi tabanı** — notlar ChromaDB'ye parçalanarak eklenir (sohbette geri getirilir).
5. **Sınav + Flashcard** — aynı notlardan sınav PDF'i ve Anki kartları (CSV/APKG) üretilir.

Her aşama `athena.pdf_engine` log isim alanından **canlı log akışına** yazılır ve her
çağrının token/maliyeti **PDF** sayacına işlenir. Üretilen tüm çıktılar PDF Otomasyonu
sayfasındaki "Geçmiş PDF'ler" listesinden indirilebilir.

- Backend imajı (`Dockerfile.worker`) tam ders-notu derlemesi için genişletilmiş TeX
  paketleri kurar: `texlive-latex-base/-extra`, `texlive-fonts-recommended`,
  `texlive-luatex`, `texlive-xetex` + `poppler-utils` (yine de `texlive-full` **değil**).
  **Ödünleşim:** imaj büyüktür ve ilk derleme yavaştır (tam pipeline tercihi).

> ⚠️ Not: `texlive-scheme-basic` bir TeX Live *şeması*dır, Debian apt paketi değildir.
> Debian/Ubuntu tabanlı imajda minimal karşılığı `texlive-latex-base`'dir. Üst akış
> TeX Live net-installer kullanacaksan Dockerfile'ı buna göre değiştirebilirsin.

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
│   ├── schemas.py              # Task(category/subtype/parent/progress/notes/materials),
│   │                           #   Note, Material, LoadAdjustment, PhysicalLoad, PdfJob
│   ├── state.py                # AthenaState (route/command/attachments)
│   ├── graph.py                # LangGraph: router(+slash) / chat / pdf / task / workout
│   ├── commands.py             # Slash komut kayıt defteri + ayrıştırıcı
│   ├── note_analyzer.py        # Notlardan metrik çıkarımı (yüksek kapasiteli model)
│   ├── subtasks.py             # AI alt görev şeması + promptu
│   ├── prompt_templates.py     # Yönlendirme + görev/plan çıkarımı + sistem promptları
│   ├── log_bus.py              # Canlı log yayını (SSE için)
│   ├── usage_callback.py       # Ajan LLM kullanımını "agent" sayacına yazar
│   └── tools.py                # Grafiğe bağlı araç sarmalayıcıları
├── db/
│   ├── sqlite_manager.py       # Async CRUD (görev/antrenman/pdf_jobs), idempotency
│   ├── chroma_manager.py       # ChromaDB: add_document (oto chunk) + query
│   └── exceptions.py
├── tools/
│   ├── agentic_tools/
│   │   ├── load_balancer.py    # calculate_cognitive_allowance (RPE×süre eşiği)
│   │   └── hardcore_mode.py    # Kod yasak, Sokratik öğretmen zinciri
│   ├── workout_import.py       # JSON/CSV/.FIT antrenman dosyası ayrıştırıcı
│   └── pdf_engine/
│       ├── wrapper.py          # process_academic_pdf (tam pipeline + ingest + iş kaydı)
│       └── automation/         # Gömülü motor: ai_client, latex_engine, usage,
│                               #   flashcard, engine_config, prompts/
├── .claude/skills/ui-ux-pro-max/  # Kurulu tasarım sistemi skill'i (search.py + veri)
└── frontend/                   # Vite + React + TS + Tailwind koyu tema, 3 sayfa
    ├── design-system/MASTER.md # Skill ile üretilen tasarım sistemi (token kaynağı)
    ├── src/{App,api,ui,main}.tsx/ts   # ui.tsx: token tabanlı Card/Button/Badge/Stat
    ├── src/index.css           # Inter fontu + semantik token'lar + odak/geçiş kuralları
    ├── src/pages/{HomePage,PdfPage,ManagePage,WorkoutsPage}.tsx
    ├── src/components/{Layout,ChatTerminal,Dropzone,LogStream,UsageMeters,
    │                   PdfHistory,TaskManager,TaskCard,Modal}.tsx
    ├── Dockerfile              # node:20-alpine build → nginx:alpine
    └── nginx.conf
```

---

## Sorun Giderme

**`/chat` 503 dönüyor / `graph_ready: false`**
OpenRouter anahtarı ayarlı değil. `OPENROUTER_API_KEY` ortam değişkenini (veya `.env`
dosyasını) ayarlayıp servisi yeniden başlat.

**Frontend'te CORS hatası**
Backend yalnızca `CORS_ORIGINS`'teki kaynaklara izin verir (varsayılan
`http://localhost:3000`). Farklı portta çalışıyorsan bu değişkeni güncelle.

**İlk başlatma yavaş**
ChromaDB ilk kullanımda `all-MiniLM-L6-v2` gömme modelini indirir. Bu tek seferlik;
sonrası önbelleğe alınır.

**PDF yükleniyor ama çıktı üretilmiyor**
Motor süreç-içidir ama OpenRouter çağrıları için `OPENROUTER_API_KEY` gerekir; anahtar
yoksa transkripsiyon başarısız olur ve iş "failed" işaretlenir. Ne olduğunu PDF
Otomasyonu sayfasındaki **canlı loglardan** anlık izleyebilirsin. Derleme için TeX
zinciri (Docker imajında gelir; yerelde `pdflatex/lualatex` kurulu olmalı) gereklidir.

**`pip install` Arch/yönetilen ortamda "externally-managed-environment" hatası**
Sistem Python'una kurma; `python3 -m venv .venv` ile sanal ortam oluşturup orada kur.

**Docker imajı `texlive-scheme-basic` bulunamadı diye derlenmiyor**
Bu bir TeX Live şemasıdır, apt paketi değil. `Dockerfile.worker` zaten doğru karşılığı
(`texlive-latex-base`) kullanır; manuel değiştirdiysen geri al.
