//! Headless deterministic Milestone 3 runner.
//!
//! `--autoplay N OUT_DIR` writes N complete replay records using the same
//! canonical Action/Input/Session path as interactive input. Default mode is a
//! terminal keyboard interface: `1` Strike, `2` Block, `3` Grab, `4` Move,
//! `w/a/s/d` radial direction, `space`
//! commit, `r` restart after a result, `q` quit.

use glam::vec3;
use just_dodge::{
    m3_cleanbox,
    milestone3::{self as m3, Action, Input, Phase, RadialDi, SeededAi, Side},
};
use sha2::{Digest, Sha256};
use std::io::{self, BufRead, Write};
use std::path::Path;

fn counter(action: Action) -> Action {
    match action {
        Action::Strike => Action::Block,
        Action::Block => Action::Grab,
        Action::Grab => Action::Strike,
        Action::Move => Action::Strike,
    }
}

fn print_state(session: &m3::Session) {
    let state = session.game.snapshot();
    println!(
        "frame={} exchange={} phase={:?} player=[head:{} torso:{} arms:{}] opponent=[head:{} torso:{} arms:{}] revealed={:?} outcome={:?} winner={:?} hash={:016x}",
        state.frame,
        state.exchange,
        state.phase,
        state.player.head_injury,
        state.player.torso_injury,
        state.player.arm_injury,
        state.opponent.head_injury,
        state.opponent.torso_injury,
        state.opponent.arm_injury,
        state.revealed,
        state.last_outcome,
        state.winner,
        session.game.truth_hash(),
    );
}

fn advance_until_input(session: &mut m3::Session, ai: SeededAi) {
    let mut world = m3_cleanbox::M3CleanboxWorld::new();
    loop {
        match session.game.snapshot().phase {
            Phase::Plan if !session.game.snapshot().opponent.committed => {
                let action = ai.choose(session.game.snapshot().exchange);
                session
                    .apply(Side::Opponent, Input::Select(action))
                    .unwrap();
                if action == Action::Move {
                    session
                        .apply(
                            Side::Opponent,
                            Input::SetRadialDi(ai.move_di(session.game.snapshot().exchange)),
                        )
                        .unwrap();
                }
                session.apply(Side::Opponent, Input::Commit).unwrap();
            }
            Phase::Plan
                if session.game.snapshot().player.committed
                    && session.game.snapshot().opponent.committed =>
            {
                session.tick();
            }
            Phase::Plan | Phase::MatchResult => return,
            _ => {
                world
                    .submit_resolve_packet(session, vec3(0.0, 0.0, 1.0), vec3(0.0, 0.0, -1.0))
                    .unwrap();
                session.tick();
            }
        }
    }
}

fn autoplay(
    seed: u64,
    destination: &Path,
) -> Result<(m3::Session, m3::Match), Box<dyn std::error::Error>> {
    let mut session = m3::Session::new(seed);
    let ai = SeededAi::new(seed);
    while session.game.snapshot().phase != Phase::MatchResult {
        advance_until_input(&mut session, ai);
        if session.game.snapshot().phase != Phase::Plan {
            continue;
        }
        let action = counter(ai.choose(session.game.snapshot().exchange));
        session.apply(Side::Player, Input::Select(action))?;
        if action == Action::Move {
            session.apply(
                Side::Player,
                Input::SetRadialDi(ai.move_di(session.game.snapshot().exchange)),
            )?;
        }
        session.apply(Side::Player, Input::Commit)?;
        advance_until_input(&mut session, ai);
    }
    session.replay.save(destination)?;
    let replayed = m3::replay(&session.replay)?;
    Ok((session, replayed))
}

fn autoplay_many(count: usize, output_dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
    std::fs::create_dir_all(output_dir)?;
    for index in 0..count {
        let seed = 0x4D33_0000_0000_0000_u64 + index as u64;
        let path = output_dir.join(format!("match_{index:02}.ron"));
        let (session, replayed) = autoplay(seed, &path)?;
        assert_eq!(session.game.snapshot(), replayed.snapshot());
        assert_eq!(session.game.truth_hash(), replayed.truth_hash());
        println!(
            "match={} seed={} winner={:?} frame={} hash={:016x} replay={}",
            index,
            seed,
            session.game.snapshot().winner,
            session.game.snapshot().frame,
            session.game.truth_hash(),
            path.display(),
        );
    }
    Ok(())
}

fn repeat_identical(count: usize, output_dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
    std::fs::create_dir_all(output_dir)?;
    let seed = 5_562_789_964_732_694_528_u64;
    let mut expected_truth = None;
    let mut expected_replay = None;
    for index in 0..count {
        let path = output_dir.join(format!("identical_{index:02}.ron"));
        let (session, replayed) = autoplay(seed, &path)?;
        assert_eq!(session.game.snapshot(), replayed.snapshot());
        assert_eq!(session.game.truth_hash(), replayed.truth_hash());
        let replay_hash: [u8; 32] = Sha256::digest(std::fs::read(&path)?).into();
        let truth_hash = session.game.truth_hash();
        assert_eq!(*expected_truth.get_or_insert(truth_hash), truth_hash);
        assert_eq!(*expected_replay.get_or_insert(replay_hash), replay_hash);
        let replay_hex = replay_hash
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        println!(
            "repeat={} seed={} winner={:?} truth={:016x} replay_sha256={}",
            index,
            seed,
            session.game.snapshot().winner,
            truth_hash,
            replay_hex,
        );
    }
    Ok(())
}

fn verify_replay(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let recorded = m3::Replay::load(path)?;
    let replayed = m3::replay(&recorded)?;
    println!(
        "verified replay={} frames={} winner={:?} hash={:016x}",
        path.display(),
        recorded.hash_trace.len(),
        replayed.snapshot().winner,
        replayed.truth_hash(),
    );
    Ok(())
}

fn manual(seed: u64) -> Result<(), Box<dyn std::error::Error>> {
    let stdin = io::stdin();
    let mut session = m3::Session::new(seed);
    let ai = SeededAi::new(seed);
    println!(
        "Milestone 3 keyboard duel: 1 Strike, 2 Block, 3 Grab, 4 Move; w/a/s/d radial DI; space commit."
    );
    print_state(&session);
    for line in stdin.lock().lines() {
        advance_until_input(&mut session, ai);
        let line = line?;
        let input = match line.trim() {
            "1" => Some(Input::Select(Action::Strike)),
            "2" => Some(Input::Select(Action::Block)),
            "3" => Some(Input::Select(Action::Grab)),
            "4" => Some(Input::Select(Action::Move)),
            "w" => Some(Input::SetRadialDi(RadialDi {
                right_q15: 0,
                forward_q15: i16::MAX,
            })),
            "s" => Some(Input::SetRadialDi(RadialDi {
                right_q15: 0,
                forward_q15: -i16::MAX,
            })),
            "a" => Some(Input::SetRadialDi(RadialDi {
                right_q15: -i16::MAX,
                forward_q15: 0,
            })),
            "d" => Some(Input::SetRadialDi(RadialDi {
                right_q15: i16::MAX,
                forward_q15: 0,
            })),
            "space" | "" => Some(Input::Commit),
            "r" => Some(Input::Restart {
                seed: session.game.snapshot().seed.wrapping_add(1),
            }),
            "q" => break,
            other => {
                eprintln!("unknown key command: {other:?}");
                None
            }
        };
        if let Some(input) = input {
            match session.apply(Side::Player, input) {
                Ok(()) => {}
                Err(error) => eprintln!("input rejected: {error:?}"),
            }
        }
        advance_until_input(&mut session, ai);
        print_state(&session);
        print!("> ");
        io::stdout().flush()?;
    }
    Ok(())
}

fn usage() -> ! {
    eprintln!(
        "usage: m3_match [--autoplay COUNT OUTPUT_DIR] [--repeat-identical COUNT OUTPUT_DIR] [--verify REPLAY.ron] [--seed U64]"
    );
    std::process::exit(2);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [] => manual(0x4D33_0000_0000_0000),
        [flag, count, output] if flag == "--autoplay" => {
            let count = count.parse()?;
            autoplay_many(count, Path::new(output))
        }
        [flag, count, output] if flag == "--repeat-identical" => {
            let count = count.parse()?;
            repeat_identical(count, Path::new(output))
        }
        [flag, replay] if flag == "--verify" => verify_replay(Path::new(replay)),
        [flag, seed] if flag == "--seed" => manual(seed.parse()?),
        _ => usage(),
    }
}
