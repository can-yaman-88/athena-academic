# TestSprite AI Testing Report (MCP) — Backend

---

## 1️⃣ Document Metadata
- **Project Name:** Jarvis (Athena-Academic)
- **Date:** 2026-06-19
- **Test Type:** Backend API
- **Environment:** Docker Compose (API :8888, production mode)
- **Prepared by:** TestSprite AI Team

---

## 2️⃣ Requirement Validation Summary

### Requirement: Dashboard & Daily Notes
- **Description:** Dashboard verisi ve günlük not kaydetme uç noktaları.

#### Test TC001 getdashboarddata_should_return_tasks_and_cognitive_load
- **Test Code:** [TC001_getdashboarddata_should_return_tasks_and_cognitive_load.py](./TC001_getdashboarddata_should_return_tasks_and_cognitive_load.py)
- **Test Error:** AssertionError: Yanıt verisi 'cognitive_capacity' anahtarını içermiyor
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/10372ea5-bf33-439a-9832-0ac2bfb6d2b6
- **Status:** ❌ Failed
- **Severity:** MEDIUM
- **Analysis / Findings:** `/dashboard_data` yanıtı `tasks` ve `pending_count` döndürüyor; test `cognitive_capacity` bekliyor. API şeması ile test beklentisi uyuşmuyor — ya API'ye bilişsel kapasite alanı eklenmeli ya da test güncellenmeli.

#### Test TC002 postdailynotes_should_save_and_autosave_daily_note
- **Test Code:** [TC002_postdailynotes_should_save_and_autosave_daily_note.py](./TC002_postdailynotes_should_save_and_autosave_daily_note.py)
- **Test Error:** AssertionError: Expected 200 or 201, got 422
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/3a36ac2e-1735-469f-9ecb-b001eb737c56
- **Status:** ❌ Failed
- **Severity:** MEDIUM
- **Analysis / Findings:** POST `/daily_notes` istek gövdesi muhtemelen yanlış format (date/content alanları gerekli). Pydantic doğrulama 422 döndürüyor.

---

### Requirement: Chat & AI Agent
- **Description:** SSE sohbet ve slash komutları.

#### Test TC003 postchat_should_process_messages_and_slash_commands
- **Test Code:** [TC003_postchat_should_process_messages_and_slash_commands.py](./TC003_postchat_should_process_messages_and_slash_commands.py)
- **Test Error:** AssertionError: Beklenmeyen durum kodu: 422
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/9646c517-a36a-4b11-871c-45ac844cd713
- **Status:** ❌ Failed
- **Severity:** HIGH
- **Analysis / Findings:** POST `/chat` istek gövdesi `message` alanı bekliyor; test muhtemelen farklı alan adı gönderiyor. API şeması doğrulanmalı.

---

### Requirement: PDF Pipeline
- **Description:** PDF yükleme ve iş geçmişi.

#### Test TC004 postupload_should_accept_pdf_files_and_create_jobs
- **Test Code:** [TC004_postupload_should_accept_pdf_files_and_create_jobs.py](./TC004_postupload_should_accept_pdf_files_and_create_jobs.py)
- **Test Error:** AssertionError: Upload failed with status 500: Internal Server Error
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/24c8b104-a4dc-424e-b8af-a5a1c5b47eb0
- **Status:** ❌ Failed
- **Severity:** HIGH
- **Analysis / Findings:** PDF yükleme 500 hatası — muhtemelen geçersiz/minimal test PDF veya arka plan işleme hatası. Sunucu logları incelenmeli.

#### Test TC005 getpdfjobs_should_return_pdf_job_history_with_statuses
- **Test Code:** [TC005_getpdfjobs_should_return_pdf_job_history_with_statuses.py](./TC005_getpdfjobs_should_return_pdf_job_history_with_statuses.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/3fb18381-f864-4ea4-9011-64cb98b740b0
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** GET `/pdf_jobs` doğru şekilde iş listesi döndürüyor.

---

### Requirement: Usage & Logging
- **Description:** API maliyet sayaçları ve canlı log akışı.

#### Test TC006 getusage_should_return_api_cost_meters_for_pdf_and_agent
- **Test Code:** [TC006_getusage_should_return_api_cost_meters_for_pdf_and_agent.py](./TC006_getusage_should_return_api_cost_meters_for_pdf_and_agent.py)
- **Test Error:** AssertionError: 'cost_usd' missing in 'pdf' cost metrics
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/adc9e58a-6bdf-441f-b5fd-69ab608410fb
- **Status:** ❌ Failed
- **Severity:** LOW
- **Analysis / Findings:** `/usage` yanıtında `total_cost_usd` kullanılıyor, test `cost_usd` bekliyor. Alan adı uyumsuzluğu.

#### Test TC007 getlogsstream_should_stream_live_system_logs
- **Test Code:** [TC007_getlogsstream_should_stream_live_system_logs.py](./TC007_getlogsstream_should_stream_live_system_logs.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/b1f75443-1dd2-49a1-abf9-4e3b4852ec4d
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** GET `/logs/stream` SSE akışı düzgün çalışıyor.

---

### Requirement: Task Management
- **Description:** Görev CRUD işlemleri.

#### Test TC008 gettasks_should_return_all_tasks_with_filters
- **Test Code:** [TC008_gettasks_should_return_all_tasks_with_filters.py](./TC008_gettasks_should_return_all_tasks_with_filters.py)
- **Test Error:** AssertionError: Failed to create academic task, status 200
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/feb5e3cc-efd6-4440-8b29-4e6a194c887f
- **Status:** ❌ Failed
- **Severity:** MEDIUM
- **Analysis / Findings:** Görev oluşturma 200 döndürüyor (başarılı) ancak test 201 bekliyor. FastAPI varsayılanı 200 — test beklentisi güncellenmeli.

#### Test TC009 posttasks_should_create_new_task
- **Test Code:** [TC009_posttasks_should_create_new_task.py](./TC009_posttasks_should_create_new_task.py)
- **Test Error:** AssertionError: Beklenmeyen durum kodu: 422
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/00335206-00f8-474c-849f-fad270f056e8
- **Status:** ❌ Failed
- **Severity:** MEDIUM
- **Analysis / Findings:** POST `/tasks` için `title` ve `deadline` zorunlu; test gövdesi eksik veya hatalı format gönderiyor.

---

### Requirement: Workout Import
- **Description:** Antrenman dosyası içe aktarma.

#### Test TC010 postworkoutsupload_should_import_workouts_from_files
- **Test Code:** [TC010_postworkoutsupload_should_import_workouts_from_files.py](./TC010_postworkoutsupload_should_import_workouts_from_files.py)
- **Test Error:** 400 Client Error: Bad Request for url: http://localhost:8888/workouts/upload
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/e1a94b63-34b6-4d7e-876f-ae3e503eb2c3/b74c5b67-d1a4-48ce-b8a9-4593ef511fd3
- **Status:** ❌ Failed
- **Severity:** MEDIUM
- **Analysis / Findings:** Yüklenen dosya formatı geçersiz veya multipart form alan adı yanlış (`file` bekleniyor).

---

## 3️⃣ Coverage & Matching Metrics

- **20%** of backend tests passed (2/10)

| Requirement              | Total Tests | ✅ Passed | ❌ Failed |
|--------------------------|-------------|-----------|-----------|
| Dashboard & Daily Notes  | 2           | 0         | 2         |
| Chat & AI Agent          | 1           | 0         | 1         |
| PDF Pipeline             | 2           | 1         | 1         |
| Usage & Logging          | 2           | 1         | 1         |
| Task Management          | 2           | 0         | 2         |
| Workout Import           | 1           | 0         | 1         |

---

## 4️⃣ Key Gaps / Risks

> 20% backend testleri geçti. 8/10 test başarısız.

**Kritik bulgular:**
- Çoğu başarısızlık **test-API şema uyumsuzluğundan** kaynaklanıyor (alan adları, HTTP status kodları), gerçek API hatalarından değil.
- `/dashboard_data` bilişsel kapasite bilgisini ayrı alan olarak döndürmüyor — frontend hesaplıyor olabilir.
- `/usage` yanıt şeması `total_cost_usd` kullanıyor, test `cost_usd` arıyor.
- POST `/tasks` başarılı oluşturmada 200 döndürüyor, REST convention 201 bekleniyor.

**Gerçek API sorunları:**
- PDF upload 500 hatası — sunucu tarafı hata, log incelemesi gerekli.
- Workout upload 400 — dosya formatı veya endpoint beklentisi uyumsuz.

**Öneriler:**
1. TestSprite testlerini gerçek API şemasına göre güncelle.
2. `/dashboard_data`'ya `cognitive_load` veya `cognitive_capacity` alanı ekle (frontend beklentisiyle uyum).
3. PDF upload 500 hatasını `docker logs athena_api` ile araştır.
4. POST endpoint'lerinde 201 Created döndürmeyi değerlendir.
