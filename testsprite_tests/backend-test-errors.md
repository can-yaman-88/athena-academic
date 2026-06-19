# Backend Test Hata Özeti

**Proje:** Jarvis (Athena-Academic)  
**Tarih:** 2026-06-19  
**Ortam:** Docker Compose — `http://localhost:8888`  
**Kaynak:** TestSprite backend test planı (10 test)

---

## Özet

| Durum | Sayı |
|-------|------|
| Geçti | 2 |
| Başarısız | 8 |
| Başarı oranı | 20% |

**Geçen testler:** TC005 (`GET /pdf_jobs`), TC007 (`GET /logs/stream`)

---

## Başarısız Testler

### TC001 — `GET /dashboard_data`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC001_getdashboarddata_should_return_tasks_and_cognitive_load.py` |
| **Endpoint** | `GET /dashboard_data` |
| **HTTP durumu** | 200 (istek başarılı, assertion başarısız) |

**Hata mesajı:**
```
AssertionError: Yanıt verisi 'cognitive_capacity' anahtarını içermiyor
```

**Traceback (özet):**
```
File "<string>", line 15, in test_getdashboarddata_should_return_tasks_and_cognitive_load
AssertionError: Yanıt verisi 'cognitive_capacity' anahtarını içermiyor
```

**Kök neden:** API yalnızca `tasks` ve `pending_count` döndürüyor. Test `cognitive_capacity` alanı bekliyor.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/10372ea5-bf33-439a-9832-0ac2bfb6d2b6

---

### TC002 — `POST /daily_notes`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC002_postdailynotes_should_save_and_autosave_daily_note.py` |
| **Endpoint** | `POST /daily_notes` |
| **HTTP durumu** | 422 Unprocessable Entity |

**Hata mesajı:**
```
AssertionError: Expected 200 or 201, got 422
```

**Traceback (özet):**
```
File "<string>", line 20, in postdailynotes_should_save_daily_note
AssertionError: Expected 200 or 201, got 422
```

**Testin gönderdiği gövde:**
```json
{ "content": "<p>Günlük not içerik testi ...</p>" }
```

**API'nin beklediği gövde** (`DailyNoteRequest`):
```json
{ "date": "2026-06-19", "content": "..." }
```

**Kök neden:** Zorunlu `date` alanı eksik.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/3a36ac2e-1735-469f-9ecb-b001eb737c56

---

### TC003 — `POST /chat`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC003_postchat_should_process_messages_and_slash_commands.py` |
| **Endpoint** | `POST /chat` |
| **HTTP durumu** | 422 Unprocessable Entity |

**Hata mesajı:**
```
AssertionError: Beklenmeyen durum kodu: 422
```

**Traceback (tam):**
```
File "<string>", line 24, in test_postchat_should_process_messages_and_slash_commands
AssertionError: Beklenmeyen durum kodu: 422

During handling of the above exception, another exception occurred:

File "<string>", line 43, in test_postchat_should_process_messages_and_slash_commands
AssertionError: Test sırasında hata: Beklenmeyen durum kodu: 422
```

**Testin gönderdiği gövde:**
```json
{
  "messages": [
    { "role": "user", "content": "Merhaba, nasılsın?" },
    { "role": "user", "content": "/yardim" },
    { "role": "user", "content": "Lütfen bana akademik öneriler ver /akademik" }
  ]
}
```

**API'nin beklediği gövde** (`ChatRequest`):
```json
{ "message": "...", "attachment_ids": [] }
```

**Kök neden:** Test OpenAI tarzı `messages` dizisi gönderiyor; API tek `message` string bekliyor.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/9646c517-a36a-4b11-871c-45ac844cd713

---

### TC004 — `POST /upload`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC004_postupload_should_accept_pdf_files_and_create_jobs.py` |
| **Endpoint** | `POST /upload` |
| **HTTP durumu** | 500 Internal Server Error |

**Hata mesajı:**
```
AssertionError: Upload failed with status 500: Internal Server Error
```

**Traceback (özet):**
```
File "<string>", line 43, in test_postupload_should_accept_pdf_files_and_create_jobs
AssertionError: Upload failed with status 500: Internal Server Error
```

**Testin gönderdiği form alanları:**
- `file`: minimal test PDF (`test.pdf`)
- `processing_instructions`: `"Test processing instructions - <uuid>"`

**API'nin beklediği form alanları:**
- `file`: PDF dosyası
- `instructions`: opsiyonel metin (varsayılan `""`)

**Kök neden:** Form alan adı uyumsuzluğu (`processing_instructions` vs `instructions`) ve/veya sunucu tarafı işleme hatası.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/24c8b104-a4dc-424e-b8af-a5a1c5b47eb0

---

### TC006 — `GET /usage`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC006_getusage_should_return_api_cost_meters_for_pdf_and_agent.py` |
| **Endpoint** | `GET /usage` |
| **HTTP durumu** | 200 (istek başarılı, assertion başarısız) |

**Hata mesajı:**
```
AssertionError: 'cost_usd' missing in 'pdf' cost metrics
```

**Traceback (özet):**
```
File "<string>", line 33, in test_getusage_should_return_api_cost_meters_for_pdf_and_agent
AssertionError: 'cost_usd' missing in 'pdf' cost metrics
```

**Testin beklediği alan:** `data.pdf.cost_usd`, `data.agent.cost_usd`

**API'nin döndürdüğü alanlar** (`UsageCategory`):
- `total_cost_usd`, `calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `avg_cost_per_call_usd`, `models`, ...

**Kök neden:** Alan adı uyumsuzluğu — API `total_cost_usd` kullanıyor, test `cost_usd` arıyor.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/adc9e58a-6bdf-441f-b5fd-69ab608410fb

---

### TC008 — `GET /tasks` (filtreleme)

| Alan | Değer |
|------|-------|
| **Dosya** | `TC008_gettasks_should_return_all_tasks_with_filters.py` |
| **Endpoint** | `POST /tasks` (oluşturma adımında başarısız) |
| **HTTP durumu** | 200 (oluşturma başarılı, assertion başarısız) |

**Hata mesajı:**
```
AssertionError: Failed to create academic task, status 200
```

**Traceback (özet):**
```
File "<string>", line 22, in test_gettasks_should_return_all_tasks_with_filters
AssertionError: Failed to create academic task, status 200
```

**Ek sorunlar (test devam etseydi):**
- Test `status: "pending"` / `"completed"` ile görev oluşturuyor; `TaskCreateRequest` `status` alanı kabul etmiyor
- `GET /tasks?category=academic` kullanıyor; API yalnızca `status` query parametresini destekliyor
- Yanıt `{"tasks": [...]}` şeklinde; test doğrudan liste bekliyor

**Kök neden:** HTTP 201 bekleniyor, API 200 döndürüyor. Ayrıca filtreleme ve yanıt şeması uyumsuz.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/feb5e3cc-efd6-4440-8b29-4e6a194c887f

---

### TC009 — `POST /tasks`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC009_posttasks_should_create_new_task.py` |
| **Endpoint** | `POST /tasks` |
| **HTTP durumu** | 422 Unprocessable Entity |

**Hata mesajı:**
```
AssertionError: Beklenmeyen durum kodu: 422
```

**Traceback (özet):**
```
File "<string>", line 22, in test_posttasks_should_create_new_task
AssertionError: Beklenmeyen durum kodu: 422
```

**Testin gönderdiği gövde:**
```json
{
  "title": "Test Görev <uuid>",
  "category": "Akademik",
  "deadline": "2026-12-31T23:59:59+00:00",
  "discipline": "Matematik",
  "estimated_hours": 3
}
```

**API'nin beklediği değerler:**
- `category`: `"academic"` veya `"daily"` (enum, Türkçe değil)
- `deadline`: ISO datetime (bu kısım geçerli olabilir)

**Kök neden:** `category: "Akademik"` geçersiz — API `academic` / `daily` bekliyor.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/00335206-00f8-474c-849f-fad270f056e8

---

### TC010 — `POST /workouts/upload`

| Alan | Değer |
|------|-------|
| **Dosya** | `TC010_postworkoutsupload_should_import_workouts_from_files.py` |
| **Endpoint** | `POST /workouts/upload` |
| **HTTP durumu** | 400 Bad Request |

**Hata mesajı:**
```
requests.exceptions.HTTPError: 400 Client Error: Bad Request for url: http://localhost:8888/workouts/upload

AssertionError: Request failed: 400 Client Error: Bad Request for url: http://localhost:8888/workouts/upload
```

**Traceback (tam):**
```
File "<string>", line 20, in post_file
requests.exceptions.HTTPError: 400 Client Error: Bad Request for url: http://localhost:8888/workouts/upload

During handling of the above exception, another exception occurred:

File "<string>", line 51, in postworkoutsupload_should_import_workouts_from_files
File "<string>", line 24, in post_file
AssertionError: Request failed: 400 Client Error: Bad Request for url: http://localhost:8888/workouts/upload
```

**Testin gönderdiği JSON içeriği:**
```json
[
  { "name": "Koşu", "duration": 3600, "RPE": 7 },
  { "name": "Bisiklet", "duration": 5400, "RPE": 6 }
]
```

**Kök neden:** Test verisi API'nin beklediği antrenman şemasıyla uyuşmuyor (`duration_minutes`, `rpe_score`, `date` vb. gerekli). CSV ve FIT dosyaları da aynı testte 400 alıyor.

**Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/b74c5b67-d1a4-48ce-b8a9-4593ef511fd3

---

## Geçen Testler

### TC005 — `GET /pdf_jobs` ✅

Endpoint iş geçmişini doğru şekilde döndürüyor; `status` alanı mevcut.

### TC007 — `GET /logs/stream` ✅

SSE canlı log akışı en az bir event ile doğrulandı.

---

## Hata Kategorileri

| Kategori | Testler | Açıklama |
|----------|---------|----------|
| **Şema uyumsuzluğu** | TC001, TC002, TC003, TC006, TC009 | Yanlış alan adı veya eksik zorunlu alan |
| **HTTP status beklentisi** | TC008 | API 200 döndürüyor, test 201 bekliyor |
| **Form alan adı** | TC004 | `processing_instructions` vs `instructions` |
| **Geçersiz test verisi** | TC010 | Workout import formatı API şemasına uymuyor |
| **Sunucu hatası** | TC004 | 500 — ayrıca log incelemesi gerekli |

---

## Önerilen Düzeltmeler

### Test tarafı (TestSprite testleri)
1. TC001: `cognitive_capacity` yerine mevcut alanları doğrula veya API'ye alan ekle
2. TC002: `date` alanını ekle
3. TC003: `{"message": "/yardim"}` formatına geç
4. TC004: Form alanını `instructions` olarak gönder
5. TC006: `total_cost_usd` alanını kontrol et
6. TC008: Status 200 kabul et; `category` query desteğini API'ye ekle veya testi kaldır
7. TC009: `category: "academic"` kullan
8. TC010: `workout_import.py` şemasına uygun örnek JSON/CSV üret

### API tarafı (isteğe bağlı iyileştirmeler)
1. `GET /dashboard_data` → `cognitive_load` veya `cognitive_capacity` ekle
2. `POST /tasks` → 201 Created döndür
3. `GET /tasks` → `category` query parametresi ekle
4. `POST /upload` → `processing_instructions` alias'ı kabul et veya 500 hatasını gider
