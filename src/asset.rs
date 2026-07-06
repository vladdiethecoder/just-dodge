use std::io::{BufReader, Read};

pub struct MeshData {
    pub vertices: Vec<f32>, // positions [x,y,z] for each vertex
    pub normals: Vec<f32>,  // normals [nx,ny,nz] for each vertex
    pub uvs: Vec<f32>,      // texture coordinates [u,v]
    pub indices: Vec<u32>,  
}

pub fn load_binary(path: &str) -> std::io::Result<MeshData> {
    let files = std::fs::File::open(path)?;
    let mut reader = BufReader::new(files);

    let mut header = [0u8; 8];
    reader.read_exact(&mut header)?;
    let vert_count = u32::from_le_bytes(header[0..4].try_into().unwrap()) as usize;
    let index_count = u32::from_le_bytes(header[4..8].try_into().unwrap()) as usize;

    let vert_bytes = vert_count * 3 * 4;
    let mut vert_data = vec![0u8; vert_bytes];
    reader.read_exact(&mut vert_data)?;
    let vertices: Vec<f32> = vert_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let mut norm_data = vec![0u8; vert_bytes];
    reader.read_exact(&mut norm_data)?;
    let normals: Vec<f32> = norm_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let index_bytes = index_count * 4;
    let mut index_data = vec![0u8; index_bytes];
    reader.read_exact(&mut index_data)?;

    let indices: Vec<u32> = index_data
        .chunks_exact(4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let uv_bytes = vert_count * 2 * 4;
    let mut uv_data = vec![0u8; uv_bytes];
    reader.read_exact(&mut uv_data)?;
    let uvs: Vec<f32> = uv_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    Ok(MeshData { vertices, normals, uvs, indices })
}