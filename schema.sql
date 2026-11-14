-- قاعدة بيانات GreenHarvest (SQLite). بتتنشأ تلقائياً عند أول تشغيل.
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  pw TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('farmer','engineer','charity','admin')),
  phone TEXT,
  city TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crops(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  planting_date TEXT,
  harvest_days INTEGER,
  field TEXT,
  notes TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS diagnoses(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  crop TEXT NOT NULL,
  symptoms TEXT,
  image TEXT,
  status TEXT NOT NULL DEFAULT 'awaiting_ai' CHECK(status IN ('awaiting_ai','done')),
  result TEXT,
  confidence REAL,
  advice TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY,
  seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  crop TEXT,
  quantity_kg REAL NOT NULL CHECK(quantity_kg > 0),
  available_kg REAL NOT NULL CHECK(available_kg >= 0),
  price_per_kg REAL NOT NULL CHECK(price_per_kg >= 0),
  city TEXT,
  harvest_date TEXT,
  description TEXT,
  image TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','sold_out','hidden')),
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  buyer_id INTEGER NOT NULL REFERENCES users(id),
  qty_kg REAL NOT NULL CHECK(qty_kg > 0),
  note TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','accepted','rejected','completed','cancelled')),
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS donations(
  id INTEGER PRIMARY KEY,
  farmer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product TEXT NOT NULL,
  qty_kg REAL NOT NULL CHECK(qty_kg > 0),
  city TEXT,
  available_from TEXT,
  status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','reserved','collected')),
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS donation_requests(
  id INTEGER PRIMARY KEY,
  donation_id INTEGER NOT NULL REFERENCES donations(id) ON DELETE CASCADE,
  charity_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'requested'
    CHECK(status IN ('requested','accepted','declined','collected')),
  pickup_time TEXT,
  pickup_place TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(donation_id, charity_id)
);

CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  link TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

-- جدول قديم (ميزة الاستشارات اتشالت من الواجهة). مفيش حذف لبيانات الموجود.
CREATE TABLE IF NOT EXISTS consultations(
  id INTEGER PRIMARY KEY,
  farmer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  engineer_id INTEGER REFERENCES users(id),
  crop TEXT,
  question TEXT NOT NULL,
  answer TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','answered')),
  created TEXT DEFAULT CURRENT_TIMESTAMP,
  answered TEXT
);

-- محادثة المساعد الذكي (Gemini): رسائل المستخدم والرد، وصور كل رسالة
CREATE TABLE IF NOT EXISTS ai_messages(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('user','assistant')),
  text TEXT NOT NULL,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_images(
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES ai_messages(id) ON DELETE CASCADE,
  filename TEXT NOT NULL UNIQUE
);
