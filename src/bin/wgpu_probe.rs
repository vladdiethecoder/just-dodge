use std::sync::Arc;
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::window::{Window, WindowId};

struct App {
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    frames: u64,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("wgpu_probe: resumed");

        let window = Arc::new(
            event_loop
                .create_window(
                    Window::default_attributes()
                        .with_title("WGPU PROBE - MAGENTA")
                        .with_inner_size(LogicalSize::new(800.0, 600.0)),
                )
                .unwrap(),
        );
        eprintln!("wgpu_probe: window created");

        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::VULKAN,
            flags: wgpu::InstanceFlags::default(),
            memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
            backend_options: wgpu::BackendOptions::default(),
            display: None,
        });
        let surface = instance.create_surface(Arc::clone(&window)).unwrap();
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            compatible_surface: Some(&surface),
            ..Default::default()
        }))
        .expect("No suitable GPU adapter found");
        let (device, queue) =
            pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default()))
                .expect("Failed to create device");

        let size = window.inner_size();
        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format: surface.get_capabilities(&adapter).formats[0],
            width: size.width.max(1),
            height: size.height.max(1),
            present_mode: wgpu::PresentMode::Fifo,
            alpha_mode: wgpu::CompositeAlphaMode::Auto,
            view_formats: vec![],
            color_space: wgpu::SurfaceColorSpace::Auto,
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);
        eprintln!("wgpu_probe: surface configured at {}x{}", config.width, config.height);

        self.window = Some(window);
        self.surface = Some(surface);
        self.device = Some(device);
        self.queue = Some(queue);
        self.config = Some(config);

        self.window.as_ref().unwrap().request_redraw();
        eprintln!("wgpu_probe: requested redraw, resumed returns");
    }

    fn about_to_wait(&mut self, _event_loop: &ActiveEventLoop) {
        if let Some(w) = self.window.as_ref() {
            w.request_redraw();
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => {
                eprintln!("wgpu_probe: close requested, exiting");
                event_loop.exit();
            }
            WindowEvent::Resized(physical) => {
                if let (Some(surface), Some(device), Some(config)) = (
                    self.surface.as_ref(),
                    self.device.as_ref(),
                    self.config.as_mut(),
                ) {
                    config.width = physical.width.max(1);
                    config.height = physical.height.max(1);
                    surface.configure(device, config);
                    eprintln!(
                        "wgpu_probe: resized to {}x{}",
                        config.width, config.height
                    );
                }
            }
            WindowEvent::RedrawRequested => {
                let Some(surface) = self.surface.as_ref() else { return };
                let Some(device) = self.device.as_ref() else { return };
                let Some(queue) = self.queue.as_ref() else { return };
                let Some(config) = self.config.as_ref() else { return };

                let frame = surface.get_current_texture();
                let surface_texture = match frame {
                    wgpu::CurrentSurfaceTexture::Success(t) => t,
                    wgpu::CurrentSurfaceTexture::Suboptimal(t) => t,
                    other => {
                        eprintln!(
                            "wgpu_probe: get_current_texture failed ({:?}), skipping",
                            std::mem::discriminant(&other)
                        );
                        return;
                    }
                };

                let view = surface_texture
                    .texture
                    .create_view(&wgpu::TextureViewDescriptor::default());

                let mut encoder =
                    device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
                {
                    let _rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                        label: Some("probe clear"),
                        color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                            view: &view,
                            resolve_target: None,
                            depth_slice: None,
                            ops: wgpu::Operations {
                                load: wgpu::LoadOp::Clear(wgpu::Color {
                                    r: 1.0,
                                    g: 0.0,
                                    b: 1.0,
                                    a: 1.0,
                                }),
                                store: wgpu::StoreOp::Store,
                            },
                        })],
                        depth_stencil_attachment: None,
                        timestamp_writes: None,
                        multiview_mask: None,
                        occlusion_query_set: None,
                    });
                }
                queue.submit(std::iter::once(encoder.finish()));
                queue.present(surface_texture);

                self.frames += 1;
                if self.frames <= 5 || self.frames % 60 == 0 {
                    eprintln!(
                        "wgpu_probe: presented frame {} ({}x{})",
                        self.frames, config.width, config.height
                    );
                }
            }
            _ => {}
        }
    }
}

fn main() {
    eprintln!("wgpu_probe: start");
    let event_loop = EventLoop::new().unwrap();
    let mut app = App {
        window: None,
        surface: None,
        device: None,
        queue: None,
        config: None,
        frames: 0,
    };
    event_loop.run_app(&mut app).unwrap();
}
