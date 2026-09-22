-- ============================================================
-- BGSBU Interacts - Demo Database Schema + Test Data
-- ============================================================
-- This SQL file contains ONLY the database schema and test
-- accounts. NO real student or personal data is included.
-- Safe for sharing and demonstration purposes.
--
-- Test Accounts:
--   Admin:   admin@demo.com    / Admin@123
--   Alumni:  alumni@test.com   / Alumni@123
--   Student: student@test.com  / Student@123
-- ============================================================

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

-- Create database
CREATE DATABASE IF NOT EXISTS `bgsbu_interacts` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `bgsbu_interacts`;

-- ============================================================
-- TABLE STRUCTURES (All 17 tables)
-- ============================================================

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `role` enum('student','alumni','admin') NOT NULL DEFAULT 'student',
  `name` varchar(100) NOT NULL,
  `email` varchar(120) NOT NULL,
  `password` varchar(255) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `profile_pic` varchar(255) DEFAULT NULL,
  `bio` text DEFAULT NULL,
  `interests` text DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `admin_notes` text DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT 1,
  `is_approved` tinyint(1) DEFAULT 0,
  `email_verified_at` timestamp NULL DEFAULT NULL,
  `approval_date` timestamp NULL DEFAULT NULL,
  `approved_by` int(11) DEFAULT NULL,
  `last_login` timestamp NULL DEFAULT NULL,
  `login_count` int(11) DEFAULT 0,
  `is_mentor` tinyint(1) DEFAULT 0,
  `mentor_verified` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_users_email` (`email`),
  KEY `idx_role` (`role`),
  KEY `idx_is_active` (`is_active`),
  KEY `idx_is_approved` (`is_approved`),
  KEY `idx_is_mentor` (`is_mentor`),
  KEY `idx_approved_by` (`approved_by`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `fk_approved_by` FOREIGN KEY (`approved_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `student_profiles`
--

DROP TABLE IF EXISTS `student_profiles`;
CREATE TABLE `student_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `roll_number` varchar(50) DEFAULT NULL,
  `joining_year` int(11) DEFAULT NULL,
  `passing_year` int(11) DEFAULT NULL,
  `student_year` int(11) DEFAULT NULL,
  `batch_year` int(11) DEFAULT NULL,
  `currently_studying` tinyint(1) DEFAULT 1,
  `internships` text DEFAULT NULL,
  `projects` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `idx_sp_joining_year` (`joining_year`),
  KEY `idx_sp_passing_year` (`passing_year`),
  KEY `idx_sp_student_year` (`student_year`),
  CONSTRAINT `student_profiles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `alumni_profiles`
--

DROP TABLE IF EXISTS `alumni_profiles`;
CREATE TABLE `alumni_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `roll_number` varchar(50) DEFAULT NULL,
  `company` varchar(200) DEFAULT NULL,
  `current_job_title` varchar(200) DEFAULT NULL,
  `job_start_date` date DEFAULT NULL,
  `passing_year` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `idx_ap_company` (`company`),
  KEY `idx_ap_passing_year` (`passing_year`),
  CONSTRAINT `alumni_profiles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `connections`
--

DROP TABLE IF EXISTS `connections`;
CREATE TABLE `connections` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `requester_id` int(11) NOT NULL,
  `recipient_id` int(11) NOT NULL,
  `status` enum('pending','accepted','rejected','blocked') DEFAULT 'pending',
  `message` text DEFAULT NULL,
  `requested_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `accepted_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_connection` (`requester_id`,`recipient_id`),
  KEY `idx_requester_id` (`requester_id`),
  KEY `idx_recipient_id` (`recipient_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `fk_recipient_id` FOREIGN KEY (`recipient_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_requester_id` FOREIGN KEY (`requester_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `messages`
--

DROP TABLE IF EXISTS `messages`;
CREATE TABLE `messages` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sender_id` int(11) NOT NULL,
  `receiver_id` int(11) NOT NULL,
  `subject` varchar(255) DEFAULT NULL,
  `content` text NOT NULL,
  `attachments` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`attachments`)),
  `is_deleted` tinyint(1) DEFAULT 0,
  `is_read` tinyint(1) DEFAULT 0,
  `read_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_sender_id` (`sender_id`),
  KEY `idx_receiver_id` (`receiver_id`),
  KEY `idx_is_read` (`is_read`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_conversation` (`sender_id`,`receiver_id`,`created_at`),
  CONSTRAINT `fk_receiver_id` FOREIGN KEY (`receiver_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sender_id` FOREIGN KEY (`sender_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `message_requests`
--

DROP TABLE IF EXISTS `message_requests`;
CREATE TABLE `message_requests` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sender_id` int(11) NOT NULL,
  `recipient_id` int(11) NOT NULL,
  `message` text DEFAULT NULL,
  `status` enum('pending','accepted','rejected') DEFAULT 'pending',
  `responded_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_request` (`sender_id`,`recipient_id`),
  KEY `idx_sender` (`sender_id`),
  KEY `idx_recipient` (`recipient_id`),
  KEY `idx_status` (`status`),
  CONSTRAINT `fk_msg_req_recipient` FOREIGN KEY (`recipient_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_msg_req_sender` FOREIGN KEY (`sender_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
CREATE TABLE `notifications` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `type` varchar(50) NOT NULL,
  `title` varchar(150) NOT NULL,
  `message` text NOT NULL,
  `related_user_id` int(11) DEFAULT NULL,
  `related_job_id` int(11) DEFAULT NULL,
  `related_mentorship_id` int(11) DEFAULT NULL,
  `action_url` varchar(255) DEFAULT NULL,
  `is_read` tinyint(1) DEFAULT 0,
  `read_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_type` (`type`),
  KEY `idx_is_read` (`is_read`),
  KEY `idx_created_at` (`created_at`),
  KEY `fk_notifications_related_user_id` (`related_user_id`),
  KEY `fk_notifications_related_job_id` (`related_job_id`),
  KEY `fk_notifications_related_mentorship_id` (`related_mentorship_id`),
  CONSTRAINT `fk_notifications_related_job_id` FOREIGN KEY (`related_job_id`) REFERENCES `jobs` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_notifications_related_mentorship_id` FOREIGN KEY (`related_mentorship_id`) REFERENCES `mentorship` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_notifications_related_user_id` FOREIGN KEY (`related_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_notifications_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
CREATE TABLE `jobs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `posted_by` int(11) NOT NULL,
  `title` varchar(150) NOT NULL,
  `description` text NOT NULL,
  `company` varchar(100) NOT NULL,
  `location` varchar(100) DEFAULT NULL,
  `job_type` enum('full-time','part-time','internship','freelance','contract') DEFAULT 'full-time',
  `experience_required` int(11) DEFAULT 0,
  `salary_min` int(11) DEFAULT NULL,
  `salary_max` int(11) DEFAULT NULL,
  `currency` varchar(10) DEFAULT 'INR',
  `skills_required` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`skills_required`)),
  `requirements` text DEFAULT NULL,
  `qualification` varchar(50) DEFAULT NULL,
  `industry` varchar(50) DEFAULT NULL,
  `company_url` varchar(255) DEFAULT NULL,
  `application_link` varchar(255) DEFAULT NULL,
  `status` enum('active','closed','draft','archived') DEFAULT 'active',
  `is_active` tinyint(1) DEFAULT 1,
  `is_approved` tinyint(1) DEFAULT 0,
  `approved_by` int(11) DEFAULT NULL,
  `posted_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `expires_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_posted_by` (`posted_by`),
  KEY `idx_status` (`status`),
  KEY `idx_is_approved` (`is_approved`),
  KEY `idx_company` (`company`),
  KEY `idx_job_type` (`job_type`),
  KEY `idx_created_at` (`created_at`),
  KEY `fk_jobs_approved_by` (`approved_by`),
  CONSTRAINT `fk_jobs_approved_by` FOREIGN KEY (`approved_by`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_jobs_posted_by` FOREIGN KEY (`posted_by`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `job_applications`
--

DROP TABLE IF EXISTS `job_applications`;
CREATE TABLE `job_applications` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `job_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `status` enum('applied','pending','reviewed','accepted','shortlisted','rejected','selected','offer_accepted') DEFAULT 'applied',
  `resume_url` varchar(255) DEFAULT NULL,
  `cover_letter` text DEFAULT NULL,
  `applied_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_application` (`job_id`,`user_id`),
  KEY `idx_job_id` (`job_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_applied_at` (`applied_at`),
  CONSTRAINT `fk_job_applications_job_id` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_job_applications_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship`
--

DROP TABLE IF EXISTS `mentorship`;
CREATE TABLE `mentorship` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mentor_id` int(11) NOT NULL,
  `mentee_id` int(11) NOT NULL,
  `status` enum('requested','accepted','active','completed','rejected') DEFAULT 'requested',
  `topic` varchar(100) DEFAULT NULL,
  `goals` text DEFAULT NULL,
  `guidance_notes` text DEFAULT NULL,
  `requested_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `accepted_at` timestamp NULL DEFAULT NULL,
  `started_at` timestamp NULL DEFAULT NULL,
  `completed_at` timestamp NULL DEFAULT NULL,
  `next_meeting` datetime DEFAULT NULL,
  `message` text DEFAULT NULL,
  `reason` text DEFAULT NULL,
  `interests` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_mentorship` (`mentor_id`,`mentee_id`),
  KEY `idx_mentor_id` (`mentor_id`),
  KEY `idx_mentee_id` (`mentee_id`),
  KEY `idx_status` (`status`),
  CONSTRAINT `fk_mentorship_mentee_id` FOREIGN KEY (`mentee_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_mentorship_mentor_id` FOREIGN KEY (`mentor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_sessions`
--

DROP TABLE IF EXISTS `mentorship_sessions`;
CREATE TABLE `mentorship_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mentorship_id` int(11) NOT NULL,
  `session_date` datetime NOT NULL,
  `meeting_link` varchar(500) DEFAULT NULL,
  `duration_minutes` int(11) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `reminder_before` int(11) DEFAULT 0,
  `feedback_from_mentor` text DEFAULT NULL,
  `feedback_from_mentee` text DEFAULT NULL,
  `rating` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_mentorship_id` (`mentorship_id`),
  KEY `idx_session_date` (`session_date`),
  CONSTRAINT `fk_mentorship_sessions_mentorship_id` FOREIGN KEY (`mentorship_id`) REFERENCES `mentorship` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_groups`
--

DROP TABLE IF EXISTS `mentorship_groups`;
CREATE TABLE `mentorship_groups` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mentor_id` int(11) NOT NULL,
  `name` varchar(200) NOT NULL,
  `description` text DEFAULT NULL,
  `domain` varchar(100) DEFAULT NULL,
  `max_members` int(11) DEFAULT 20,
  `is_active` tinyint(1) DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_group_mentor` (`mentor_id`),
  KEY `idx_group_domain` (`domain`),
  KEY `idx_group_active` (`is_active`),
  CONSTRAINT `fk_group_mentor` FOREIGN KEY (`mentor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_group_members`
--

DROP TABLE IF EXISTS `mentorship_group_members`;
CREATE TABLE `mentorship_group_members` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `status` enum('pending','approved','rejected') DEFAULT 'pending',
  `joined_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_group_member` (`group_id`,`user_id`),
  KEY `idx_group_member_group` (`group_id`),
  KEY `idx_group_member_user` (`user_id`),
  CONSTRAINT `fk_group_member_group` FOREIGN KEY (`group_id`) REFERENCES `mentorship_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_group_member_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_group_messages`
--

DROP TABLE IF EXISTS `mentorship_group_messages`;
CREATE TABLE `mentorship_group_messages` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `content` text NOT NULL,
  `attachments` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`attachments`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_group_msg_group` (`group_id`),
  KEY `idx_group_msg_user` (`user_id`),
  CONSTRAINT `fk_group_msg_group` FOREIGN KEY (`group_id`) REFERENCES `mentorship_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_group_msg_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_group_announcements`
--

DROP TABLE IF EXISTS `mentorship_group_announcements`;
CREATE TABLE `mentorship_group_announcements` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `title` varchar(200) NOT NULL,
  `content` text NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_group_announce_group` (`group_id`),
  KEY `idx_group_announce_user` (`user_id`),
  CONSTRAINT `fk_group_announce_group` FOREIGN KEY (`group_id`) REFERENCES `mentorship_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_group_announce_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_tasks`
--

DROP TABLE IF EXISTS `mentorship_tasks`;
CREATE TABLE `mentorship_tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) DEFAULT NULL,
  `mentorship_id` int(11) DEFAULT NULL,
  `created_by` int(11) NOT NULL,
  `assigned_to` int(11) DEFAULT NULL,
  `title` varchar(200) NOT NULL,
  `description` text DEFAULT NULL,
  `deadline` date DEFAULT NULL,
  `status` enum('pending','in_progress','completed','cancelled') DEFAULT 'pending',
  `submission_file` varchar(500) DEFAULT NULL,
  `submission_link` varchar(500) DEFAULT NULL,
  `feedback` text DEFAULT NULL,
  `completed_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_task_group` (`group_id`),
  KEY `idx_task_mentorship` (`mentorship_id`),
  KEY `idx_task_creator` (`created_by`),
  KEY `idx_task_assigned` (`assigned_to`),
  CONSTRAINT `fk_task_assigned` FOREIGN KEY (`assigned_to`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_task_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_task_group` FOREIGN KEY (`group_id`) REFERENCES `mentorship_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_task_mentorship` FOREIGN KEY (`mentorship_id`) REFERENCES `mentorship` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `mentorship_resources`
--

DROP TABLE IF EXISTS `mentorship_resources`;
CREATE TABLE `mentorship_resources` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mentor_id` int(11) NOT NULL,
  `group_id` int(11) DEFAULT NULL,
  `mentorship_id` int(11) DEFAULT NULL,
  `title` varchar(200) NOT NULL,
  `description` text DEFAULT NULL,
  `resource_type` enum('pdf','link','note','video','course','material') DEFAULT 'link',
  `url` varchar(500) DEFAULT NULL,
  `file_path` varchar(500) DEFAULT NULL,
  `domain` varchar(100) DEFAULT NULL,
  `is_public` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_resource_mentor` (`mentor_id`),
  KEY `idx_resource_group` (`group_id`),
  KEY `idx_resource_mentorship` (`mentorship_id`),
  KEY `idx_resource_domain` (`domain`),
  CONSTRAINT `fk_resource_group` FOREIGN KEY (`group_id`) REFERENCES `mentorship_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_resource_mentor` FOREIGN KEY (`mentor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_resource_mentorship` FOREIGN KEY (`mentorship_id`) REFERENCES `mentorship` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `event_type` varchar(50) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `details` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `user_otps`
--

DROP TABLE IF EXISTS `user_otps`;
CREATE TABLE `user_otps` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `otp_hash` varchar(255) NOT NULL,
  `purpose` enum('email_verification','password_reset','password_change') NOT NULL,
  `expires_at` datetime NOT NULL,
  `attempts` tinyint(4) NOT NULL DEFAULT 0,
  `is_used` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_uo_user_purpose` (`user_id`,`purpose`,`is_used`),
  KEY `idx_uo_expires` (`expires_at`),
  CONSTRAINT `user_otps_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `user_skills`
--

DROP TABLE IF EXISTS `user_skills`;
CREATE TABLE `user_skills` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `skill` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_skill` (`user_id`,`skill`),
  KEY `idx_skill` (`skill`),
  CONSTRAINT `user_skills_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `work_experiences`
--

DROP TABLE IF EXISTS `work_experiences`;
CREATE TABLE `work_experiences` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `job_title` varchar(200) NOT NULL,
  `company` varchar(200) NOT NULL,
  `role` varchar(200) DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `is_current` tinyint(1) NOT NULL DEFAULT 0,
  `description` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_we_user` (`user_id`),
  KEY `idx_we_company` (`company`),
  CONSTRAINT `work_experiences_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `system_protocols`
--

DROP TABLE IF EXISTS `system_protocols`;
CREATE TABLE `system_protocols` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `protocol_type` varchar(50) NOT NULL,
  `is_enabled` tinyint(1) DEFAULT 1,
  `max_messages_per_day` int(11) DEFAULT NULL,
  `message_retention_days` int(11) DEFAULT NULL,
  `require_connection_for_messaging` tinyint(1) DEFAULT 0,
  `auto_delete_messages` tinyint(1) DEFAULT 0,
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `protocol_type` (`protocol_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `system_settings`
--

DROP TABLE IF EXISTS `system_settings`;
CREATE TABLE `system_settings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) NOT NULL,
  `setting_value` text NOT NULL,
  `data_type` varchar(20) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `is_public` tinyint(1) DEFAULT 0,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `setting_key` (`setting_key`),
  KEY `idx_setting_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- TEST DATA ONLY - NO REAL PERSONAL DATA
-- ============================================================

-- Test Admin Account
-- Email: admin@demo.com  Password: Admin@123
INSERT INTO `users` (`id`, `role`, `name`, `email`, `password`, `phone`, `is_active`, `is_approved`, `email_verified_at`, `created_at`, `updated_at`)
VALUES (1, 'admin', 'Admin User', 'admin@demo.com',
  '$2b$12$LJ3m4ris7EHF5SxnGvnMuOXx4GSR2TlGqa3NxIZ8T4d5bHpBOSJaG',
  '+91-0000000000', 1, 1, NOW(), NOW(), NOW());

-- Test Alumni Account
-- Email: alumni@test.com  Password: Alumni@123
INSERT INTO `users` (`id`, `role`, `name`, `email`, `password`, `department`, `is_active`, `is_approved`, `email_verified_at`, `is_mentor`, `created_at`, `updated_at`)
VALUES (2, 'alumni', 'Test Alumni', 'alumni@test.com',
  '$2b$12$LJ3m4ris7EHF5SxnGvnMuOXx4GSR2TlGqa3NxIZ8T4d5bHpBOSJaG',
  'Computer Science & Engineering', 1, 1, NOW(), 1, NOW(), NOW());

INSERT INTO `alumni_profiles` (`user_id`, `roll_number`, `company`, `current_job_title`, `passing_year`)
VALUES (2, 'TEST-ALUMNI-001', 'Demo Tech Corp', 'Software Engineer', 2022);

INSERT INTO `user_skills` (`user_id`, `skill`) VALUES
  (2, 'Python'), (2, 'JavaScript'), (2, 'React');

-- Test Student Account
-- Email: student@test.com  Password: Student@123
INSERT INTO `users` (`id`, `role`, `name`, `email`, `password`, `department`, `is_active`, `is_approved`, `email_verified_at`, `created_at`, `updated_at`)
VALUES (3, 'student', 'Test Student', 'student@test.com',
  '$2b$12$LJ3m4ris7EHF5SxnGvnMuOXx4GSR2TlGqa3NxIZ8T4d5bHpBOSJaG',
  'Computer Science & Engineering', 1, 1, NOW(), NOW(), NOW());

INSERT INTO `student_profiles` (`user_id`, `roll_number`, `joining_year`, `passing_year`, `student_year`, `currently_studying`)
VALUES (3, 'TEST-STU-001', 2024, 2028, 2, 1);

/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
