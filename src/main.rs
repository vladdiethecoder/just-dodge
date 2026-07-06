use std::sync::Arc;
use winit::application::ApplicationHandler;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::window::{Window, WindowId};

mod renderer;
mod input;
mod asset;
mod motion;
mod combat;

struct App {
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    renderer: Option<renderer::Renderer>,
}

impl ApplicationHandler for App {

    fn resumed(&mut self, event_loop: &ActiveEventLoop) {

        // 1. Create the window (wrapped in Arc so surface can hold 'static ref)
        let window = Arc::new(
            event_loop
                .create_window(Window::default_attributes().with_title("Just Dodge"))
                .unwrap(),
        );

        // 2. Create wgpu instance
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::default());

        // 3. Create surface from the window (Arc keeps the window alive for 'static)
        let surface = instance.create_surface(Arc::clone(&window)).unwrap();

        // 4. Request adapter (async via pollster)
        let adapter = pollster::block_on(instance.request_adapter(
            &wgpu::RequestAdapterOptions {
                compatible_surface: Some(&surface),
                ..Default::default()
            },
        )).expect("No suitable GPU adapter found");

        // 5. Request device + queue (async via pollster)
        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor::default(),
            None,
        )).expect("Failed to create device");

        // 6. Configure swapchain
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

        // 7. Store everything
        self.renderer = Some(renderer::Renderer::new(&device, &config, &queue));
        self.window = Some(window);
        self.surface = Some(surface);
        self.device = Some(device);
        self.queue = Some(queue);
        self.config = Some(config);

        // 8. Request the first redraw
        self.window.as_ref().unwrap().request_redraw();
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => {
                event_loop.exit();
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
                    let projection = glam::Mat4::perspective_lh(
                        std::f32::consts::FRAC_PI_4,
                        aspect,
                        0.1,
                        100.0,
                    );

                    let view_matrix = glam::Mat4::look_at_lh(
                        glam::vec3(2.0, 2.0, 2.0),
                        glam::vec3(0.0, 0.0, 0.0),
                        glam::vec3(0.0, 1.0, 0.0),
                    );
                    let mvp = projection * view_matrix;

                    queue.write_buffer(
                        &renderer.uniform_buffer,
                        0,
                        bytemuck::bytes_of(&[mvp]),
                    );

                    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
                    {
                        let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                            label: None,
                            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                view: &view,
                                resolve_target: None,
                                ops: wgpu::Operations {
                                    load: wgpu::LoadOp::Clear(wgpu::Color {
                                        r: 0.1,
                                        g: 0.1,
                                        b: 0.2,
                                        a: 1.0,
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
                        renderer.render_arena(&mut rpass);
                        renderer.render_mannequin(&mut rpass);
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
    };
    event_loop.run_app(&mut app).unwrap();
}
