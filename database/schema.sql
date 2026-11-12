CREATE DATABASE IF NOT EXISTS mealbridge
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE mealbridge;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL,
  organization_name VARCHAR(150),
  phone VARCHAR(30),
  address TEXT,
  latitude DOUBLE,
  longitude DOUBLE,
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_users_role (role)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS food_categories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS food_donations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  donor_id INT NOT NULL,
  category_id INT NOT NULL,
  food_name VARCHAR(150) NOT NULL,
  description TEXT,
  quantity INT NOT NULL,
  meals INT NOT NULL,
  image_filename VARCHAR(255),
  preparation_time DATETIME NOT NULL,
  expiry_time DATETIME NOT NULL,
  pickup_address TEXT NOT NULL,
  latitude DOUBLE,
  longitude DOUBLE,
  status VARCHAR(20) NOT NULL DEFAULT 'available',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_food_donations_donor_id (donor_id),
  INDEX ix_food_donations_category_id (category_id),
  INDEX ix_food_donations_expiry_time (expiry_time),
  INDEX ix_food_donations_status (status),
  CONSTRAINT fk_food_donations_donor FOREIGN KEY (donor_id) REFERENCES users(id),
  CONSTRAINT fk_food_donations_category FOREIGN KEY (category_id) REFERENCES food_categories(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ngo_verification (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ngo_id INT NOT NULL UNIQUE,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  notes TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ngo_verification_user FOREIGN KEY (ngo_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pickup_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  donation_id INT NOT NULL,
  ngo_id INT NOT NULL,
  donor_id INT NOT NULL,
  pickup_date DATETIME NOT NULL,
  pickup_time VARCHAR(50),
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  notes TEXT,
  requested_quantity INT,
  requested_meals INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_pickup_requests_donation_id (donation_id),
  INDEX ix_pickup_requests_ngo_id (ngo_id),
  INDEX ix_pickup_requests_donor_id (donor_id),
  INDEX ix_pickup_requests_status (status),
  CONSTRAINT fk_pickup_requests_donation FOREIGN KEY (donation_id) REFERENCES food_donations(id),
  CONSTRAINT fk_pickup_requests_ngo FOREIGN KEY (ngo_id) REFERENCES users(id),
  CONSTRAINT fk_pickup_requests_donor FOREIGN KEY (donor_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(120),
  message TEXT NOT NULL,
  type VARCHAR(50),
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_notifications_user_id (user_id),
  INDEX ix_notifications_is_read (is_read),
  CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pickup_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  donation_id INT NOT NULL,
  ngo_id INT NOT NULL,
  donor_id INT NOT NULL,
  completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notes TEXT,
  quantity INT NOT NULL DEFAULT 0,
  meals INT NOT NULL DEFAULT 0,
  CONSTRAINT fk_pickup_history_donation FOREIGN KEY (donation_id) REFERENCES food_donations(id),
  CONSTRAINT fk_pickup_history_ngo FOREIGN KEY (ngo_id) REFERENCES users(id),
  CONSTRAINT fk_pickup_history_donor FOREIGN KEY (donor_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reports (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reporter_id INT NOT NULL,
  subject VARCHAR(150) NOT NULL,
  details TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_reports_reporter_id (reporter_id),
  INDEX ix_reports_status (status),
  CONSTRAINT fk_reports_reporter FOREIGN KEY (reporter_id) REFERENCES users(id)
) ENGINE=InnoDB;
