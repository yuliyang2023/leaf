use std::{env, process};

fn main() {
    let mut args = env::args().skip(1);
    let mut config = String::from("leaf.json");
    let mut test = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "-c" | "--config" => {
                config = args.next().unwrap_or_else(|| {
                    eprintln!("missing configuration path");
                    process::exit(2);
                });
            }
            "-T" | "--test" => test = true,
            "-V" | "--version" => {
                println!("leaf-oray {} (SOCKS5 + VMess TCP)", env!("CARGO_PKG_VERSION"));
                return;
            }
            "-h" | "--help" => {
                println!("leaf-oray [-c CONFIG.json] [-T] [-V]\nSOCKS5 inbound + VMess TCP outbound; single-threaded runtime.");
                return;
            }
            _ => {
                eprintln!("unknown argument: {arg}");
                process::exit(2);
            }
        }
    }
    if test {
        match leaf::test_config(&config) {
            Ok(()) => println!("ok"),
            Err(error) => {
                eprintln!("configuration error: {error}");
                process::exit(1);
            }
        }
        return;
    }
    let options = leaf::StartOptions {
        config: leaf::Config::File(config),
        runtime_opt: leaf::RuntimeOption::SingleThread,
    };
    if let Err(error) = leaf::start(0, options) {
        eprintln!("leaf start failed: {error}");
        process::exit(1);
    }
}
