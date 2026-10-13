-- Database schema for the BINA case study (MariaDB).
-- Matches the schema shown in the case study (docs/case-study.pdf, figure 5).

CREATE DATABASE IF NOT EXISTS bina CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bina;

-- One row per country, loaded from data/supplemental/countries-extended.csv
-- (ISO-3166 countries with regional codes).
CREATE TABLE country (
    id                       INT(11)  NOT NULL AUTO_INCREMENT,
    name                     CHAR(48) NOT NULL,
    alpha_2                  CHAR(2),
    alpha_3                  CHAR(3),
    code                     INT(11),
    iso_3166_2               CHAR(24),
    region                   CHAR(48),
    subregion                CHAR(48),
    intermediate_region      CHAR(48),
    region_code              INT(11),
    subregion_code           INT(11),
    intermediate_region_code INT(11),
    PRIMARY KEY (id),
    UNIQUE KEY uq_country_name (name)
);

-- Name and description of each indicator, e.g. "Happiness Score".
CREATE TABLE metric_definition (
    id          INT(11)      NOT NULL AUTO_INCREMENT,
    name        CHAR(255)    NOT NULL,
    description TEXT,
    PRIMARY KEY (id),
    UNIQUE KEY uq_metric_definition_name (name)
);

-- One value of one indicator for one country in one year.
CREATE TABLE metric (
    id                INT(11) NOT NULL AUTO_INCREMENT,
    value             FLOAT,
    year              INT(11) NOT NULL,
    country           INT(11) NOT NULL,
    metric_definition INT(11) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_metric_country           FOREIGN KEY (country)           REFERENCES country (id),
    CONSTRAINT fk_metric_metric_definition FOREIGN KEY (metric_definition) REFERENCES metric_definition (id)
);
