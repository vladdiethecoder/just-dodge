use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::window::{Window, WindowId};

struct App {
    window: Option<Window>,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("winit_probe: resumed");
        let window = event_loop
            .create_window(
                Window::default_attributes()
                    .with_title("WINIT PROBE - SELECT ME")
                    .with_inner_size(LogicalSize::new(800.0, 600.0)),
            )
            .unwrap();
        eprintln!("winit_probe: window created");
        self.window = Some(window);
    }

    fn window_event(&mut self, event_loop: &ActiveEventLoop, _id: WindowId, event: WindowEvent) {
        match event {
            WindowEvent::CloseRequested => {
                eprintln!("winit_probe: close requested, exiting");
                event_loop.exit();
            }
            WindowEvent::Resized(size) => {
                eprintln!("winit_probe: resized to {}x{}", size.width, size.height);
            }
            _ => {}
        }
    }
}

fn main() {
    eprintln!("winit_probe: start");
    let event_loop = EventLoop::new().unwrap();
    let mut app = App { window: None };
    event_loop.run_app(&mut app).unwrap();
}
