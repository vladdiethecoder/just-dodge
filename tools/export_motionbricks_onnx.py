"""
MotionBricks ONNX Export — Phase 1
Exports VQVAE (encoder + decoder), codebook, pose backbone, root backbone.

Usage:
    export MOTIONBRICKS_DIR=/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks
    source /run/media/vdubrov/Bulk-SSD/mb_venv/bin/activate
    python tools/export_motionbricks_onnx.py
"""
import sys, os, json

MB_DIR = os.environ.get("MOTIONBRICKS_DIR",
    "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks")
sys.path.insert(0, MB_DIR)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
os.makedirs(OUT_DIR, exist_ok=True)

import torch
import torch.nn as nn
import numpy as np

# ---------------------------------------------------------------------------
# 1. Model instantiation helpers
# ---------------------------------------------------------------------------

def resolve_hydra_refs(cfg, root=None):
    """Recursively resolve Hydra-style ${path.to.key} interpolations in a dict."""
    if root is None:
        root = cfg
    
    def resolve_value(v):
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            path = v[2:-1].split(".")
            node = root
            for key in path:
                if isinstance(node, dict):
                    node = node.get(key, v)
                else:
                    return v
            # Resolve recursively in case of nested refs
            return resolve_value(node)
        return v
    
    if isinstance(cfg, dict):
        return {k: resolve_hydra_refs(v, root) for k, v in cfg.items()}
    elif isinstance(cfg, list):
        return [resolve_hydra_refs(v, root) for v in cfg]
    elif isinstance(cfg, str):
        return resolve_value(cfg)
    return cfg

RESOLVED_CACHE = {}

def load_yaml_cfg(path):
    """Read Hydra YAML config and resolve interpolations."""
    import yaml
    with open(path) as f:
        raw = yaml.safe_load(f)
    resolved = resolve_hydra_refs(raw)
    return resolved

def build_motion_rep(cfg):
    """Instantiate the motion representation from hparams."""
    from motionbricks.motionlib.core.skeletons.g1 import G1Skeleton34
    from motionbricks.motionlib.core.motion_reps.dual_root_global_joints import GlobalRootGlobalJoints
    from motionbricks.motionlib.core.utils.stats import Stats

    skel_cfg = cfg.get("skeleton", {})
    skeleton = G1Skeleton34(t_pose=skel_cfg.get("t_pose", "capture"))
    
    motion_rep_cfg = cfg.get("motion_rep", {})
    stats_folder = motion_rep_cfg.get("stats", {}).get("folder", "")
    if stats_folder and not os.path.isabs(stats_folder):
        # All hparams paths are relative to MB_DIR
        stats_folder = os.path.join(MB_DIR, stats_folder)
    stats = Stats(folder=stats_folder)
    
    motion_rep = GlobalRootGlobalJoints(
        name=cfg.get("motion_rep", {}).get("name", "g1skel34_dual_root_global_joints"),
        stats=stats,
        skeleton=skeleton,
        fps=cfg.get("fps", 30),
    )
    return motion_rep

def build_pose_vqvae(hparams, motion_rep):
    """Instantiate the VQVAE network from hparams."""
    from motionbricks.vqvae.neural_modules.vqvae import VQVAE
    vq_cfg = hparams["model"]["pose_vqvae_network"]
    
    # Feature modes from hparams
    feat_mode = vq_cfg.get("feature_mode", [
        "joint_positions_and_rotations_and_hip_height",  # encoder input
        "pose",                                            # decoder input
        "joint_positions_and_rotations_and_hip_height",   # target cond
        "root_without_hip_height_without_heading",        # external cond
    ])
    
    vqvae = VQVAE(
        pose_root_mode=vq_cfg.get("pose_root_mode", "pose"),
        motion_rep=motion_rep,
        encoder_state_dim=vq_cfg.get("encoder_state_dim", 241),
        decoder_state_dim=vq_cfg.get("decoder_state_dim", 329),
        decoder_target_cond_dim=vq_cfg.get("decoder_target_cond_dim", 241),
        decoder_external_cond_dim=vq_cfg.get("decoder_external_cond_dim", 2),
        feature_mode=feat_mode,
        quantizer_strategy=vq_cfg.get("quantizer_strategy", "multihead_ema_reset"),
        quantizer_mu=vq_cfg.get("quantizer_mu", 0.99),
        nb_code=vq_cfg.get("nb_code", 100000000),
        code_dim=vq_cfg.get("code_dim", 256),
        output_emb_width=vq_cfg.get("output_emb_width", 256),
        down_t=vq_cfg.get("down_t", 2),
        stride_t=vq_cfg.get("stride_t", 2),
        width=vq_cfg.get("width", 512),
        depth=vq_cfg.get("depth", 4),
        dilation_growth_rate=vq_cfg.get("dilation_growth_rate", 3),
        activation=vq_cfg.get("activation", "relu"),
        num_heads=vq_cfg.get("num_heads", 8),
        kmeans_init=vq_cfg.get("kmeans_init", False),
        norm=vq_cfg.get("norm", None),
        calculate_per_head_perplexity=vq_cfg.get("calculate_per_head_perplexity", True),
        cond_fusion_last_layer=vq_cfg.get("cond_fusion_last_layer", False),
    )
    return vqvae

def build_pose_backbone(hparams, motion_rep):
    """Instantiate the pose backbone network from hparams."""
    from motionbricks.motion_backbone.neural_modules.pose_backbone import pose_backbone_network
    
    backbone_cfg = hparams["model"]["backbone_network"]
    args_cfg = backbone_cfg["args"]
    # Merge top-level args
    top_args = hparams["model"].get("args", {})
    full_args = {}
    full_args.update(args_cfg)
    full_args.update(top_args)
    
    backbone = pose_backbone_network(motion_rep=motion_rep, args=full_args)
    return backbone, full_args

def build_root_backbone(hparams, motion_rep):
    """Instantiate the root backbone network from hparams."""
    from motionbricks.motion_backbone.neural_modules.root_backbone import root_backbone_network
    
    backbone_cfg = hparams["model"]["backbone_network"]
    args_cfg = backbone_cfg["args"]
    top_args = hparams["model"].get("args", {})
    full_args = {}
    full_args.update(args_cfg)
    full_args.update(top_args)
    
    backbone = root_backbone_network(args=full_args, motion_rep=motion_rep)
    return backbone, full_args

# ---------------------------------------------------------------------------
# 2. Export wrappers
# ---------------------------------------------------------------------------

class EncoderExportWrapper(nn.Module):
    """Wraps VQVAE encoder + quantization into one ONNX model.
    Input:  [1, encoder_input_dim, T]  (channels-first, feature-extracted)
    Output: [1, code_dim_per_head, T/4, num_heads]  (quantized features)
    """
    def __init__(self, vqvae):
        super().__init__()
        self.encoder = vqvae.encoder
        # The quantizer's embed: [num_heads, nb_code_per_head, code_dim_per_head]
        self.register_buffer('codebook', vqvae.quantizer.vq._codebook.embed.data.clone())
        self._num_heads = vqvae._num_heads
    
    def forward(self, x):
        # x: [B, F, T] where F = encoder_input_dim (feature-extracted input)
        encoded = self.encoder(x)  # [B, code_dim, T/4]
        # codebook: [num_heads, nb_code, code_dim_per_head]
        # encoded:  [B, code_dim, T/4] where code_dim = num_heads * code_dim_per_head
        B, C, T = encoded.shape
        code_dim_per_head = C // self._num_heads
        
        # Reshape for multi-head lookup
        encoded_r = encoded.view(B, self._num_heads, code_dim_per_head, T)  # [B, H, D, T]
        encoded_r = encoded_r.permute(0, 1, 3, 2)  # [B, H, T, D]
        
        # Compute distances against codebook [H, N, D]
        # encoded_r: [B, H, T, D] -> [B, H, T, 1, D]
        # codebook:  [1, H, 1, N, D]
        cb = self.codebook[None, :, None, :, :]  # [1, H, 1, N, D]
        feat = encoded_r[:, :, :, None, :]  # [B, H, T, 1, D]
        
        dists = torch.sum((feat - cb) ** 2, dim=-1)  # [B, H, T, N]
        indices = dists.argmin(dim=-1)  # [B, H, T] — per-head per-position indices
        
        # Decode: look up codebook values at indices
        # indices: [B, H, T] -> lookup in codebook [H, N, D]
        # Output: [B, H, T, D] -> [B, C, T]
        decoded = self.codebook[None, :, :, :].expand(B, -1, -1, -1)  # [B, H, N, D]
        # Gather: for each B, H, T, pick index N
        gathered = torch.zeros(B, self._num_heads, T, code_dim_per_head, device=x.device)
        for h in range(self._num_heads):
            idx_h = indices[:, h, :]  # [B, T]
            for b in range(B):
                gathered[b, h, :, :] = self.codebook[h, idx_h[b, :], :]
        
        output = gathered.permute(0, 1, 3, 2).reshape(B, C, T)  # [B, C, T]
        return output, indices


class DecoderExportWrapper(nn.Module):
    """Wraps VQVAE decoder for ONNX export.
    Input:  [1, code_dim, T/4]  (quantized, channels-first)
    Input:  [1, T, target_cond_dim] (optional, can be zeros)
    Input:  [1, T, external_cond_dim] (optional, can be zeros)
    Output: [1, T, decoder_state_dim]  (decoded motion, channels-last)
    """
    def __init__(self, vqvae):
        super().__init__()
        self.decoder = vqvae.decoder
        self._extract_feature = vqvae.extract_feature
    
    def forward(self, x_quantized, target_cond=None, external_cond=None):
        # x_quantized: [B, C, T/4]
        # Decoder expects channels-first for conv input
        x_decoder = self.decoder(x_quantized, external_cond, target_cond, None)
        # x_decoder: [B, decoder_state_dim, T]
        return x_decoder.permute(0, 2, 1)  # [B, T, decoder_state_dim]


class PoseBackboneExportWrapper(nn.Module):
    """Wraps pose backbone for ONNX export.
    Input:  tokens [B, N, 8]  int64
    Input:  root_values [B, N*4, 4]  float32
    Input:  pose_cond [B, N*4, feat_dim]  float32 (zeros if unused)
    Input:  has_pose_cond [B, N*4]  float32 (zeros for no cond)
    Input:  num_tokens [B, 1]  int64
    Output: pose_logits [B, N, 8, nb_code_per_head]
    """
    def __init__(self, backbone):
        super().__init__()
        self.backbone = backbone
    
    def forward(self, pose_tokens, local_root_values, pose_cond, has_pose_cond, num_tokens):
        output = self.backbone(pose_tokens, local_root_values, pose_cond, has_pose_cond, num_tokens)
        return output['pose_logits']


class RootBackboneExportWrapper(nn.Module):
    """Wraps root backbone for ONNX export.
    Input:  global_root_values [B, 8, 5]
    Input:  has_global_root_values [B, 8]
    Input:  local_root_values [B, 8, 4]
    Input:  has_local_root_values [B, 8]
    Input:  poses [B, 8, feat_dim]
    Input:  has_poses [B, 8]
    Input:  num_tokens [B, 1]
    Output: pred_global_root_values [B, maxTokens*4, 5]
    Output: num_token_logits [B, num_token_classes]
    """
    def __init__(self, backbone):
        super().__init__()
        self.backbone = backbone
    
    def forward(self, global_root_values, has_global_root_values, local_root_values,
                has_local_root_values, poses, has_poses, num_tokens):
        output = self.backbone(global_root_values, has_global_root_values,
                              local_root_values, has_local_root_values,
                              poses, has_poses, num_tokens)
        return output['pred_global_root_values'], output['num_token_logits']


# ---------------------------------------------------------------------------
# 3. Main export
# ---------------------------------------------------------------------------

def export_vqvae(pose_model):
    """Export VQVAE encoder + decoder + codebook."""
    vqvae = pose_model.supporting_nets['pose_net']
    vqvae.eval().to('cpu')
    
    # Determine motion rep name
    motion_rep_name = vqvae._motion_rep.name  # 'local' or 'global'
    print(f"VQVAE motion rep: {motion_rep_name}, encoder_in: {vqvae.encoder.model[0].in_channels}")
    
    # Get encoder input dim from feature extraction
    dummy = torch.zeros(1, 1, 1000)
    encoder_input_dim = vqvae.extract_feature(dummy, vqvae.encoder_input_feature_mode).shape[-1]
    print(f"Encoder input dim (after feature extraction): {encoder_input_dim}")
    
    code_dim = vqvae.code_dim  # 256
    codebook = vqvae.quantizer.vq._codebook.embed.data.clone()  # [8, 10, 32]
    print(f"Codebook shape: {codebook.shape}")
    
    # Export encoder
    T = 64  # 64 frames = 16 tokens (4 frames/token)
    dummy_input = torch.randn(1, encoder_input_dim, T)
    
    # Create combined encoder+quantizer wrapper
    enc_wrapper = EncoderExportWrapper(vqvae)
    enc_wrapper.eval()
    
    torch.onnx.export(
        enc_wrapper, dummy_input,
        os.path.join(OUT_DIR, "motionbricks_vqvae_encoder.onnx"),
        input_names=['input_frames'],
        output_names=['quantized', 'indices'],
        opset_version=17,
        dynamic_axes={
            'input_frames': {2: 'time'},
            'quantized': {2: 'time'},
            'indices': {2: 'time'},
        },
    )
    print("✅ VQVAE encoder + quantizer exported")
    
    # Export decoder
    T_out = T // 4  # down_t=2 → 4x compression
    dummy_quantized = torch.randn(1, code_dim, T_out)
    dummy_target_cond = torch.zeros(1, T, vqvae.decoder._target_cond_dim)
    dummy_external_cond = torch.zeros(1, T, vqvae.decoder._external_cond_dim)
    if vqvae.decoder._external_cond_dim <= 0:
        dummy_external_cond = None
    
    dec_wrapper = DecoderExportWrapper(vqvae)
    dec_wrapper.eval()
    
    torch.onnx.export(
        dec_wrapper, (dummy_quantized, dummy_target_cond, dummy_external_cond),
        os.path.join(OUT_DIR, "motionbricks_vqvae_decoder.onnx"),
        input_names=['quantized', 'target_cond', 'external_cond'],
        output_names=['reconstructed_motion'],
        opset_version=17,
        dynamic_axes={
            'quantized': {2: 'time'},
            'target_cond': {1: 'time'},
            'external_cond': {1: 'time'},
            'reconstructed_motion': {1: 'time'},
        },
    )
    print("✅ VQVAE decoder exported")
    
    # Save codebook as .npy
    cb_path = os.path.join(OUT_DIR, "motionbricks_codebook.npy")
    np.save(cb_path, codebook.numpy())
    print(f"✅ Codebook saved: {cb_path} [{codebook.shape}]")


def export_pose_backbone(pose_model):
    """Export the pose backbone transformer."""
    backbone = pose_model.backbone_net
    backbone.eval().to('cpu')
    
    # Clear motion_rep references to avoid torch.export issues with Stats.__hash__
    # All projections are already built, forward() doesn't need these
    _saved = (backbone.motion_rep, backbone.global_motion_rep, backbone.local_motion_rep)
    backbone.motion_rep = None
    backbone.global_motion_rep = None
    backbone.local_motion_rep = None
    
    # Determine dimensions
    num_pose_heads, _ = backbone.get_num_heads()  # (8, 1)
    num_codes, _ = backbone.get_num_codes(include_aug_tokens=True)  # (11, ?)
    num_frames_per_token = backbone.get_num_frames_per_token()  # 4
    local_root_dim = backbone._args.get('local_root_dim', 4)
    pose_feat_width = backbone._args.get('pose_feat_width', 640)
    
    N = 8  # tokens
    batch = 1
    
    print(f"Pose backbone: {num_pose_heads} heads, {num_codes} codes/head, {num_frames_per_token} frames/token")
    
    dummy_tokens = torch.randint(0, num_codes, (batch, N, num_pose_heads)).long()
    dummy_root = torch.randn(batch, N * num_frames_per_token, local_root_dim).float()
    dummy_pose_cond = torch.zeros(batch, N * num_frames_per_token, backbone._args['local_pose_dim']).float()
    dummy_has_pose = torch.zeros(batch, N * num_frames_per_token).float()
    dummy_num_tokens = torch.tensor([[N]]).long()
    
    wrapper = PoseBackboneExportWrapper(backbone)
    wrapper.eval()
    
    torch.onnx.export(
        wrapper, (dummy_tokens, dummy_root, dummy_pose_cond, dummy_has_pose, dummy_num_tokens),
        os.path.join(OUT_DIR, "motionbricks_pose_backbone.onnx"),
        input_names=['pose_tokens', 'local_root_values', 'pose_cond', 'has_pose_cond', 'num_tokens'],
        output_names=['pose_logits'],
        opset_version=17,
        dynamic_axes={
            'pose_tokens': {1: 'num_tokens'},
            'local_root_values': {1: 'num_frames'},
            'pose_cond': {1: 'num_frames'},
            'has_pose_cond': {1: 'num_frames'},
            'pose_logits': {1: 'num_tokens'},
        },
    )
    print("✅ Pose backbone exported")
    # Restore motion_rep
    backbone.motion_rep, backbone.global_motion_rep, backbone.local_motion_rep = _saved


def export_root_backbone(root_model):
    """Export the root backbone network."""
    backbone = root_model.backbone_net
    backbone.eval().to('cpu')
    
    # Clear motion_rep references to avoid torch.export issues
    _saved = (backbone.motion_rep, backbone.global_motion_rep, backbone.local_motion_rep)
    backbone.motion_rep = None
    backbone.global_motion_rep = None
    backbone.local_motion_rep = None
    
    max_tokens = backbone._args['max_tokens']  # 16
    num_frames_per_token = backbone.get_num_frames_per_token()  # 4
    local_pose_dim = backbone._args.get('local_pose_dim', 329)
    
    batch = 1
    num_frames = 8  # constraint frames
    
    print(f"Root backbone: max_tokens={max_tokens}, frames_per_token={num_frames_per_token}")
    
    dummy_global_root = torch.randn(batch, num_frames, 5).float()
    dummy_has_global = torch.ones(batch, num_frames).float()
    dummy_local_root = torch.randn(batch, num_frames, 4).float()
    dummy_has_local = torch.ones(batch, num_frames).float()
    dummy_poses = torch.randn(batch, num_frames, local_pose_dim).float()
    dummy_has_poses = torch.ones(batch, num_frames).float()
    dummy_num_tokens = torch.tensor([[8]]).long()
    
    wrapper = RootBackboneExportWrapper(backbone)
    wrapper.eval()
    
    torch.onnx.export(
        wrapper, (dummy_global_root, dummy_has_global, dummy_local_root, dummy_has_local,
                 dummy_poses, dummy_has_poses, dummy_num_tokens),
        os.path.join(OUT_DIR, "motionbricks_root_backbone.onnx"),
        input_names=['global_root_values', 'has_global_root', 'local_root_values', 'has_local_root',
                    'poses', 'has_poses', 'num_tokens'],
        output_names=['pred_global_root', 'num_token_logits'],
        opset_version=17,
        dynamic_axes={
            'pred_global_root': {1: 'num_frames'},
        },
    )
    print("✅ Root backbone exported")
    backbone.motion_rep, backbone.global_motion_rep, backbone.local_motion_rep = _saved


def main():
    import yaml
    print("=" * 60)
    print("MotionBricks ONNX Export")
    print("=" * 60)
    
    base = os.path.join(MB_DIR, "out")
    
    # -----------------------------------------------------------------------
    # Load pose model
    # -----------------------------------------------------------------------
    print("\n--- Loading Pose Model ---")
    pose_hparams = load_yaml_cfg(f"{base}/motionbricks_pose/version_1/hparams.yaml")
    motion_rep = build_motion_rep(pose_hparams)
    
    vqvae = build_pose_vqvae(pose_hparams, motion_rep)
    pose_backbone, pose_args = build_pose_backbone(pose_hparams, motion_rep)
    
    # Load VQVAE weights from the separate VQVAE checkpoint
    vqvae_ckpt = torch.load(f"{base}/motionbricks_vqvae/version_1/checkpoints/model-step=2000000.ckpt",
                            map_location='cpu', weights_only=True)
    vqvae_sd = {}
    for k, v in vqvae_ckpt['state_dict'].items():
        if k.startswith('pose_net.'):
            vqvae_sd[k.replace('pose_net.', '')] = v
    # Patch decoder final layer if size mismatches (known 1-channel diff)
    if 'decoder.model.6.weight' in vqvae_sd:
        ckpt_out = vqvae_sd['decoder.model.6.weight'].shape[0]
        if vqvae.decoder.model[6].weight.shape[0] != ckpt_out:
            print(f"Patching decoder output from {vqvae.decoder.model[6].weight.shape[0]} to {ckpt_out}")
            # Rebuild the final conv layer with correct output channels
            old_conv = vqvae.decoder.model[6]
            import torch.nn as nn
            new_conv = nn.Conv1d(old_conv.in_channels, ckpt_out, old_conv.kernel_size,
                                 stride=old_conv.stride, padding=old_conv.padding,
                                 dilation=old_conv.dilation, groups=old_conv.groups,
                                 bias=old_conv.bias is not None)
            vqvae.decoder.model[6] = new_conv
    missing, unexpected = vqvae.load_state_dict(vqvae_sd, strict=False)
    print(f"VQVAE: {len(vqvae_sd)} keys loaded, {len(missing)} missing, {len(unexpected)} unexpected")
    vqvae.eval()
    
    # Load pose backbone weights from the pose checkpoint
    pose_ckpt = torch.load(f"{base}/motionbricks_pose/version_1/checkpoints/model-step=2000000.ckpt",
                           map_location='cpu', weights_only=True)
    pose_sd = pose_ckpt['state_dict']
    
    # Load backbone weights  
    back_sd = {}
    for k, v in pose_sd.items():
        if k.startswith('backbone_net.'):
            back_sd[k.replace('backbone_net.', '')] = v
    missing, unexpected = pose_backbone.load_state_dict(back_sd, strict=False)
    print(f"Pose backbone: {len(back_sd)} keys loaded, {len(missing)} missing, {len(unexpected)} unexpected")
    pose_backbone.eval()
    
    # Create a simple container for export functions
    class PoseModelContainer:
        pass
    pose_model = PoseModelContainer()
    pose_model.supporting_nets = {'pose_net': vqvae}
    pose_model.backbone_net = pose_backbone
    
    # -----------------------------------------------------------------------
    # Export VQVAE
    # -----------------------------------------------------------------------
    print("\n--- Exporting VQVAE ---")
    export_vqvae(pose_model)
    
    # -----------------------------------------------------------------------
    # Export Pose Backbone
    # -----------------------------------------------------------------------
    print("\n--- Exporting Pose Backbone ---")
    export_pose_backbone(pose_model)
    
    # -----------------------------------------------------------------------
    # Load Root Model
    # -----------------------------------------------------------------------
    print("\n--- Loading Root Model ---")
    root_hparams = load_yaml_cfg(f"{base}/motionbricks_root/version_1/hparams.yaml")
    root_backbone, root_args = build_root_backbone(root_hparams, motion_rep)
    
    root_ckpt = torch.load(f"{base}/motionbricks_root/version_1/checkpoints/model-step=2000000.ckpt",
                           map_location='cpu', weights_only=True)
    root_sd = root_ckpt['state_dict']
    
    back_sd = {}
    for k, v in root_sd.items():
        if k.startswith('backbone_net.'):
            back_sd[k.replace('backbone_net.', '')] = v
    missing, unexpected = root_backbone.load_state_dict(back_sd, strict=False)
    print(f"Root backbone: {len(back_sd)} keys loaded, {len(missing)} missing, {len(unexpected)} unexpected")
    root_backbone.eval()
    
    class RootModelContainer:
        pass
    root_model = RootModelContainer()
    root_model.backbone_net = root_backbone
    
    # -----------------------------------------------------------------------
    # Export Root Backbone
    # -----------------------------------------------------------------------
    print("\n--- Exporting Root Backbone ---")
    export_root_backbone(root_model)
    
    print(f"\n{'=' * 60}")
    print(f"All ONNX models exported to {OUT_DIR}")
    print(f"{'=' * 60}")
    
    # List outputs
    for f in sorted(os.listdir(OUT_DIR)):
        if f.endswith('.onnx') or f.endswith('.npy'):
            size = os.path.getsize(os.path.join(OUT_DIR, f))
            print(f"  {f}: {size:,} bytes")


if __name__ == '__main__':
    main()
