-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 00 · Setup: catalog, schemas, volume
-- MAGIC Run once. On Databricks Free Edition, if `CREATE CATALOG` is not permitted,
-- MAGIC replace `energy` with the default `workspace` catalog everywhere (and in `.env`).

-- COMMAND ----------

CREATE CATALOG IF NOT EXISTS energy;

-- COMMAND ----------

CREATE SCHEMA IF NOT EXISTS energy.raw    COMMENT 'Landing volume + Auto Loader checkpoints';
CREATE SCHEMA IF NOT EXISTS energy.bronze COMMENT 'Raw API responses, append-only';
CREATE SCHEMA IF NOT EXISTS energy.silver COMMENT 'Cleaned, typed, deduplicated';
CREATE SCHEMA IF NOT EXISTS energy.gold   COMMENT 'Analytics-ready models (built by dbt)';

-- COMMAND ----------

CREATE VOLUME IF NOT EXISTS energy.raw.landing     COMMENT 'Raw JSON files uploaded by energy-ingest';
CREATE VOLUME IF NOT EXISTS energy.raw.checkpoints COMMENT 'Auto Loader schema + checkpoint state';
