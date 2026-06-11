fn main() {
    println!("Melosviz desktop entrypoint");
}

#[cfg(test)]
mod tests {
    use ctrlc;

    #[test]
    fn test_ctrlc_set_handler() {
        ctrlc::set_handler(|| println!("Received Ctrl+C")).unwrap();
    }
}
