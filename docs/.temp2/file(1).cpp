struct ArmorPiece {
    BoneID          covered_bone;
    ArmorMaterial   material;
    float           integrity;          // 0.0 - 1.0
    float           mass_kg;
    float           slash_resist;
    float           pierce_resist;
    float           blunt_resist;
    float           cleave_resist;
    JointROMClamp   rom_clamp;          // fed to MotionBricks style weights
    float           noise_level;
    bool            destructible;       // Warden pieces = false
    MeshID          visual_mesh;        // swappable per integrity state
    MeshID          destroyed_mesh;     // exposed bone/flesh mesh
};
