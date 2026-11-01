-- ============================================================================
-- schema.sql — 岗位库 schema（**一个岗位一个库**：data/chat/<job_code>/job.db）
-- ============================================================================
-- 决策（2026-09-15 老板拍板）：
--   ① 一岗一库（不做"总库"）；② **不做跨岗复用/人才库**；
--   ③ 只要保证"**本岗内候选人不重复**"即可。
-- 为什么一岗一库：数据跟岗位走（岗位目录=全项目对齐键）→ "关闭/删除岗位"就是挪目录，
--   库跟着走；总库那种"岗位早没了、库里留孤儿行"的问题自然消失（旧 business.db 就出过这毛病）。
--
-- ⚠️ 纪律：**这份 schema 是唯一来源**（N 个岗位库都用它建）。改字段 = 改这里 + 升 user_version +
--   在 job_db._migrate 里加一段升级；否则 N 个库会各自漂。
-- ⚠️ 本文件必须**幂等**（全部 IF NOT EXISTS），因为 _migrate 每次开库都会跑它。
-- ============================================================================

PRAGMA user_version = 2;
-- v2（2026-09-16）：去掉 UNIQUE(job_code, content_hash)（它会误伤"两个 id 不同、原文相同的人"→ 丢人）；
--   content_hash 保留为普通列 + 普通索引（复核信号）。migrate 里对 v1 的老库重建 candidates 表。

-- ── 岗位元信息（单行；好处：单独拷一个库出去也知道这是哪个岗）────────────────
CREATE TABLE IF NOT EXISTS job_meta (
  job_code   TEXT PRIMARY KEY,
  title      TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

-- ── 候选人（本岗内去重）────────────────────────────────────────────────────
-- 去重口径（2026-09-16 修正，v2）：
--   1) UNIQUE(job_code, source_id)  主锚点 = 猎聘 res_id_encode（同一人第二次采到 → 更新不新增）
--   2) content_hash 只做**复核信号**（sha1(岗位号 + 简历原文)），**不再做唯一约束**。
--      ⚠️ 为什么改：原先 UNIQUE(job_code, content_hash) 本意是"换了 id、原文一样 → 同一人"，
--      但实测（2026-09-16 单测抓到）它会**把两个 id 不同、原文恰好相同的人当成一个人，直接丢一行**——
--      这是"丢人"，比"多留一行"贵得多。source_id 本身就是可靠主锚点，兜底不该是唯一约束。
--   3) 匹配层 match_results.raw_hash 输入指纹（同输入不重复付费）
CREATE TABLE IF NOT EXISTS candidates (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  job_code         TEXT NOT NULL,
  source_platform  TEXT NOT NULL DEFAULT 'liepin',
  source_id        TEXT NOT NULL,              -- 猎聘 res_id_encode
  source_url       TEXT DEFAULT '',
  content_hash     TEXT,                       -- sha1(job_code \x1f raw_content)；raw 空 = NULL；**非唯一**
  raw_content      TEXT DEFAULT '',            -- 详情页全文（没开详情时为空）
  summary_text     TEXT DEFAULT '',            -- 列表卡片原文（本地粗筛的原料，不开详情就有）
  display_name     TEXT DEFAULT '',
  display_company  TEXT DEFAULT '',
  display_position TEXT DEFAULT '',
  active_badge     TEXT DEFAULT '',            -- 活跃度徽章（今天活跃/3天内/30天内…）
  structured       TEXT DEFAULT '{}',          -- 卡片能结构化出来的字段（城市/学历/年限/期望…）JSON
  local_score      REAL,                       -- 本地粗筛分（0-100；规则+关键词，0 token）
  local_hits       TEXT DEFAULT '[]',          -- 命中的关键词/规则 JSON（**可解释**：凭什么说它靠谱）
  round_tag        TEXT DEFAULT '',            -- 哪一轮采到的（关键字+条件标签）
  status           TEXT DEFAULT 'new',         -- new/kept/opened/dropped/contacted/…
  collected_by     TEXT DEFAULT '',
  collected_account TEXT DEFAULT '',
  first_seen_at    TEXT DEFAULT '',
  last_seen_at     TEXT DEFAULT '',
  updated_at       TEXT DEFAULT '',
  UNIQUE(job_code, source_id)
);
CREATE INDEX IF NOT EXISTS idx_cand_job    ON candidates(job_code);
CREATE INDEX IF NOT EXISTS idx_cand_score  ON candidates(job_code, local_score);
CREATE INDEX IF NOT EXISTS idx_cand_hash   ON candidates(job_code, content_hash);

-- ── 匹配结果（逐人评分；带输入指纹缓存）─────────────────────────────────
CREATE TABLE IF NOT EXISTS match_results (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  job_code                TEXT NOT NULL,
  candidate_id            INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  total_score             INTEGER,
  verdict                 TEXT DEFAULT '',      -- 推荐/待定/不推荐
  confidence              TEXT DEFAULT '',      -- 高/中/低
  score_skill             INTEGER,              -- 四维分（wails 里有列无值，我们保留列：将来要拆维再用）
  score_exp               INTEGER,
  score_edu               INTEGER,
  score_city              INTEGER,
  match_points            TEXT DEFAULT '[]',    -- JSON：匹配点（= 话术原料）
  concerns                TEXT DEFAULT '[]',    -- JSON：疑虑点
  summary                 TEXT DEFAULT '',
  detail_json             TEXT DEFAULT '{}',
  special_notes_snapshot  TEXT DEFAULT '',
  raw_hash                TEXT DEFAULT '',      -- sha256(岗位文本 \x1f 候选人文本 \x1f 特别提醒)
  created_at              TEXT DEFAULT '',
  updated_at              TEXT DEFAULT '',
  UNIQUE(job_code, candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_match_job ON match_results(job_code);

-- ── 沟通/跟进记录（台账：打招呼、回复、面试、offer…）─────────────────────
CREATE TABLE IF NOT EXISTS candidate_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  job_code     TEXT NOT NULL,
  event_type   TEXT NOT NULL,     -- 打招呼/回复/面试/offer/入职/不合适/备注
  note         TEXT DEFAULT '',
  account      TEXT DEFAULT '',
  created_at   TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ev_cand ON candidate_events(candidate_id);
CREATE INDEX IF NOT EXISTS idx_ev_job  ON candidate_events(job_code);

-- ── 列表页原文临时池（本地粗筛的原料；算完可清空）───────────────────────
-- 用途：翻页时先把整页原文丢进来（不解析、不判断），本地规则再从中取字段/算命中率。
CREATE TABLE IF NOT EXISTS pool_samples (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_text     TEXT NOT NULL,
  round_tag    TEXT DEFAULT '',
  collected_at TEXT DEFAULT ''
);
