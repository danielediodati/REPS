-- The exercises' image paths are gone from the vendored dataset: upstream
-- took the pictures from other sites.
ALTER TABLE exercises DROP COLUMN images;
