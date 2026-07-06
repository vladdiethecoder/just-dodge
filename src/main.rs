use glam::{Mat4, Vec3, vec3};
use std::sync::Arc;
use winit::application::ApplicationHandler;
use winit::event::{ElementState, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::Key;
use winit::window::{Window, WindowId};

mod asset;
mod combat;
mod input;
mod motion;
mod renderer;

struct Camera {
    theta: f32,
    phi: f32,
    radius: f32,
    dragging: bool,
    last_mouse: (f64, f64),
}

impl Camera {
    fn new() -> Self {
        Self {
            theta: std::f32::consts::FRAC_PI_4,
            phi: std::f32::consts::FRAC_PI_4,
            radius: 5.0,
            dragging: false,
            last_mouse: (0.0, 0.0),
        }
    }

    fn proj_view(&self, aspect: f32) -> Mat4 {
        let eye = vec3(
            self.radius * self.phi.sin() * self.theta.sin(),
            self.radius * self.phi.cos(),
            self.radius * self.phi.sin() * self.theta.cos(),
        );
        let view = Mat4::look_at_lh(eye, Vec3::ZERO, Vec3::Y);
        let proj = Mat4::perspective_lh(std::f32::consts::FRAC_PI_4, aspect, 0.1, 100.0);
        proj * view
    }
}

struct App {
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    renderer: Option<renderer::Renderer>,
    camera: Camera,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        let window = Arc::new(
            event_loop
                .create_window(Window::default_attributes().with_title("Just Dodge — Arena"))
                .unwrap(),
        );

        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::VULKAN,
            ..Default::default()
        });
        let surface = instance.create_surface(Arc::clone(&window)).unwrap();
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            compatible_surface: Some(&surface),
            ..Default::default()
        }))
        .expect("No suitable GPU adapter found");
        let (device, queue) =
            pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default(), None))
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
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);

        self.renderer = Some(renderer::Renderer::new(&device, &config, &queue));
        self.window = Some(window);
        self.surface = Some(surface);
        self.device = Some(device);
        self.queue = Some(queue);
        self.config = Some(config);

        self.window.as_ref().unwrap().request_redraw();
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => event_loop.exit(),

            WindowEvent::MouseInput { state, button, .. } => {
                if button == MouseButton::Left {
                    self.camera.dragging = state == ElementState::Pressed;
                }
            }

            WindowEvent::CursorMoved { position, .. } => {
                if self.camera.dragging {
                    let dx = position.x - self.camera.last_mouse.0;
                    let dy = position.y - self.camera.last_mouse.1;
                    self.camera.theta -= dx as f32 * 0.005;
                    self.camera.phi = (self.camera.phi - dy as f32 * 0.005)
                        .clamp(0.1, std::f32::consts::PI - 0.1);
                }
                self.camera.last_mouse = (position.x, position.y);
            }

            WindowEvent::MouseWheel { delta, .. } => {
                let scroll = match delta {
                    MouseScrollDelta::LineDelta(_, y) => y,
                    MouseScrollDelta::PixelDelta(p) => p.y as f32 * 0.1,
                };
                self.camera.radius = (self.camera.radius - scroll * 0.5).clamp(1.0, 20.0);
            }

            WindowEvent::RedrawRequested => {
                if let (Some(surface), Some(device), Some(queue), Some(renderer), Some(config)) = (
                    self.surface.as_ref(),
                    self.device.as_ref(),
                    self.queue.as_ref(),
                    self.renderer.as_ref(),
                    self.config.as_ref(),
                ) {
                    let frame = surface.get_current_texture().unwrap();
                    let view = frame.texture.create_view(&wgpu::TextureViewDescriptor::default());

                    let aspect = config.width as f32 / config.height as f32;
                    let proj_view = self.camera.proj_view(aspect);

                    for obj in &renderer.objects {
                        let mvp = proj_view * obj.model;
                        queue.write_buffer(&obj.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
                    }

                    let mut encoder =
                        device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
                    {
                        let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                            label: None,
                            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                view: &view,
                                resolve_target: None,
                                ops: wgpu::Operations {
                                    load: wgpu::LoadOp::Clear(wgpu::Color {
                                        r: 0.05, g: 0.05, b: 0.08, a: 1.0,
                                    }),
                                    store: wgpu::StoreOp::Store,
                                },
                            })],
                            depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                                view: &renderer.depth_view,
                                depth_ops: Some(wgpu::Operations {
                                    load: wgpu::LoadOp::Clear(1.0),
                                    store: wgpu::StoreOp::Store,
                                }),
                                stencil_ops: None,
                            }),
                            timestamp_writes: None,
                            occlusion_query_set: None,
                        });
                        renderer.render(&mut rpass);
                    }
                    queue.submit(std::iter::once(encoder.finish()));
                    frame.present();
                }
                self.window.as_ref().unwrap().request_redraw();
            }

            WindowEvent::KeyboardInput { event, .. } => {
                if let Some(action) = input::handle_key(&event) {
                    println!("Action: {:?}", action);
                }
                if event.state == ElementState::Pressed {
                    if let Key::Character(c) = &event.logical_key {
                        if c.as_str() == "r" {
                            self.camera = Camera::new();
                            println!("Camera reset");
                        }
                    }
                }
            }

            _ => {}
        }
    }
}

fn main() {
    let event_loop = EventLoop::new().unwrap();
    let mut app = App {
        window: None,
        surface: None,
        device: None,
        queue: None,
        config: None,
        renderer: None,
        camera: Camera::new(),
    };
    event_loop.run_app(&mut app).unwrap();
}
