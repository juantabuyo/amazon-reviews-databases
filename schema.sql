-- Structured part of the submitted MySQL schema, with no destructive statements.

CREATE TABLE IF NOT EXISTS usuarios (
            reviewerID VARCHAR(64) NOT NULL,
            reviewerName VARCHAR(255) NULL,
            PRIMARY KEY (reviewerID)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS articulos (
            asin VARCHAR(32) NOT NULL,
            categoria VARCHAR(64) NOT NULL,
            PRIMARY KEY (asin)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS reviews (
            review_id BIGINT NOT NULL AUTO_INCREMENT,
            reviewerID VARCHAR(64) NOT NULL,
            asin VARCHAR(32) NOT NULL,
            overall DECIMAL(3,1) NULL,
            helpful_1 INT NULL,
            helpful_2 INT NULL,
            unixReviewTime BIGINT NULL,
            reviewTime DATE NULL,
            categoria VARCHAR(64) NOT NULL,
            PRIMARY KEY (review_id),
            FOREIGN KEY (reviewerID) REFERENCES usuarios(reviewerID),
            FOREIGN KEY (asin) REFERENCES articulos(asin)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
