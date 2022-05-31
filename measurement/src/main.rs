use rocksdb::{IteratorMode};
use clap::Parser;
#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    #[clap(short, long)]
    db_path: String,
}

fn main() {
    let args = Args::parse();
    let db = rocksdb::DB::open_default(&args.db_path).unwrap();
    let it = db.iterator(IteratorMode::Start);
    let total_value_length = it.fold(0, |acc, (_key, value)| {
        println!("{}", value.len());
        acc + value.len()
    });
    println!("Total value length of {}:\n{} bytes", &args.db_path, total_value_length);
}