CREATE TABLE upd(
    client_name TEXT,
    epoch_id INT,
    file_path TEXT,
    PRIMARY KEY(client_name, epoch_id)
);

CREATE TABLE nev(
    client_name TEXT,
    epoch_id INT,
    PRIMARY KEY(client_name, epoch_id)
);