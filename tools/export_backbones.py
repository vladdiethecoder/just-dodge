"""
Export MotionBricks transformer + linear projection weights for Rust inference.
Strategy: export the pure TransformerEncoder stack as ONNX, extract all 
projection/embedding weights as .npy files. Rust handles the embedding logic.

Run AFTER export_motionbricks_onnx.py (which handles VQVAE).
"""
import sys, os, json

MB_DIR = os.environ.get("MOTIONBRICKS_DIR",
    "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks")
sys.path.insert(0, MB_DIR)
sys.path.insert(0, os.path.dirname(__file__))

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")

import torch
import torch.nn as nn
import numpy as np

# Patch Stats.__hash__ to avoid .numpy() call during torch.export
from motionbricks.motionlib.core.utils.stats import Stats
Stats.__hash__ = lambda self: id(self)

from export_motionbricks_onnx import (
    load_yaml_cfg, build_motion_rep, build_pose_vqvae, build_pose_backbone, build_root_backbone,
)

def save_tensor(t, path):
    np.save(path, t.detach().cpu().numpy())

def main():
    base = os.path.join(MB_DIR, "out")
    
    # ---- Load models ----
    print("--- Loading Models ---")
    pose_hparams = load_yaml_cfg(f"{base}/motionbricks_pose/version_1/hparams.yaml")
    motion_rep = build_motion_rep(pose_hparams)
    
    vqvae = build_pose_vqvae(pose_hparams, motion_rep)
    pose_backbone, _ = build_pose_backbone(pose_hparams, motion_rep)
    
    # Load VQVAE weights
    vqvae_ckpt = torch.load(f"{base}/motionbricks_vqvae/version_1/checkpoints/model-step=2000000.ckpt",
                            map_location='cpu', weights_only=True)
    vqvae_sd = {k.replace('pose_net.', ''): v for k, v in vqvae_ckpt['state_dict'].items() if k.startswith('pose_net.')}
    if 'decoder.model.6.weight' in vqvae_sd:
        if vqvae.decoder.model[6].weight.shape[0] != vqvae_sd['decoder.model.6.weight'].shape[0]:
            old = vqvae.decoder.model[6]
            vqvae.decoder.model[6] = nn.Conv1d(old.in_channels, vqvae_sd['decoder.model.6.weight'].shape[0],
                old.kernel_size, stride=old.stride, padding=old.padding,
                dilation=old.dilation, groups=old.groups, bias=old.bias is not None)
    vqvae.load_state_dict(vqvae_sd, strict=False); vqvae.eval()
    
    # Load pose backbone
    pose_ckpt = torch.load(f"{base}/motionbricks_pose/version_1/checkpoints/model-step=2000000.ckpt",
                           map_location='cpu', weights_only=True)
    back_sd = {k.replace('backbone_net.', ''): v for k, v in pose_ckpt['state_dict'].items() if k.startswith('backbone_net.')}
    pose_backbone.load_state_dict(back_sd, strict=False); pose_backbone.eval()
    
    # ---- Export Pose Transformer (pure encoder only) ----
    print("\n--- Exporting Pose Transformer ---")
    transformer = pose_backbone._transformer_model
    
    batch, n_tokens, n_embd = 1, 8, pose_backbone._args['n_embd']
    dummy = torch.randn(batch, n_tokens, n_embd)
    
    # Export transformer as ONNX
    torch.onnx.export(
        transformer, dummy,
        os.path.join(OUT_DIR, "motionbricks_pose_transformer.onnx"),
        input_names=['hidden_states'],
        output_names=['output'],
        opset_version=17,
        do_constant_folding=True,
        dynamic_axes={'hidden_states': {1: 'num_tokens'}, 'output': {1: 'num_tokens'}},
    )
    print("✅ Pose transformer exported")
    
    # ---- Extract pose backbone weights ----
    print("\n--- Extracting Pose Backbone Weights ---")
    for name, param in pose_backbone.named_parameters():
        fname = f"poseb_{name.replace('.', '_')}.npy"
        save_tensor(param, os.path.join(OUT_DIR, fname))
    print(f"✅ {sum(1 for _ in pose_backbone.parameters())} pose backbone params extracted")
    
    # ---- Export Root Transformer (both shared and root-token) ----
    print("\n--- Exporting Root Backbone ---")
    root_hparams = load_yaml_cfg(f"{base}/motionbricks_root/version_1/hparams.yaml")
    root_backbone, _ = build_root_backbone(root_hparams, motion_rep)
    
    root_ckpt = torch.load(f"{base}/motionbricks_root/version_1/checkpoints/model-step=2000000.ckpt",
                           map_location='cpu', weights_only=True)
    back_sd = {k.replace('backbone_net.', ''): v for k, v in root_ckpt['state_dict'].items() if k.startswith('backbone_net.')}
    root_backbone.load_state_dict(back_sd, strict=False); root_backbone.eval()
    
    # Export shared transformer
    shared_transformer = root_backbone._shared_transformer_model
    dummy_r = torch.randn(1, 10, root_backbone._args['n_embd'])  # 1 + 2*frames/token
    torch.onnx.export(
        shared_transformer, dummy_r,
        os.path.join(OUT_DIR, "motionbricks_root_shared.onnx"),
        input_names=['hidden_states'],
        output_names=['output'],
        opset_version=17,
        do_constant_folding=True,
        dynamic_axes={'hidden_states': {1: 'seq'}, 'output': {1: 'seq'}},
    )
    print("✅ Root shared transformer exported")
    
    # Export root-token transformer if present
    if root_backbone._root_token_transformer_model is not None:
        rt_transformer = root_backbone._root_token_transformer_model
        # seq = 1 (num_token emb) + 2*frames/token (frame emb) + max_tokens (position emb)
        dummy_rt = torch.randn(1, 1 + 8 + root_backbone._args['max_tokens'], root_backbone._args['n_embd'])
        torch.onnx.export(
            rt_transformer, dummy_rt,
            os.path.join(OUT_DIR, "motionbricks_root_token.onnx"),
            input_names=['hidden_states'],
            output_names=['output'],
            opset_version=17,
            do_constant_folding=True,
            dynamic_axes={'hidden_states': {1: 'seq'}, 'output': {1: 'seq'}},
        )
        print("✅ Root-token transformer exported")
    
    # Export conv decoder (DoubleCondDecoder)
    conv = root_backbone._conv_output
    # Input: second_stage_output_emb [B, n_embd, maxTokens], external_cond [B, n_embd, totalFrames], etc.
    n_embd_r = root_backbone._args['n_embd']
    max_tokens = root_backbone._args['max_tokens']
    num_frames_per_token = root_backbone.get_num_frames_per_token()
    total_frames = max_tokens * num_frames_per_token
    
    class ConvExport(nn.Module):
        def __init__(self, conv):
            super().__init__()
            self.conv = conv
        def forward(self, x, external_cond, target_cond):
            return self.conv(x, external_cond=external_cond, target_cond=target_cond, 
                           has_target_cond=None, token_mask=None)
    
    conv_wrapper = ConvExport(conv).eval()
    dummy_x = torch.randn(1, n_embd_r, max_tokens)
    dummy_ext = torch.randn(1, total_frames, n_embd_r)
    dummy_tgt = torch.randn(1, total_frames, root_backbone._args['global_root_dim'])
    
    torch.onnx.export(
        conv_wrapper, (dummy_x, dummy_ext, dummy_tgt),
        os.path.join(OUT_DIR, "motionbricks_root_conv.onnx"),
        input_names=['hidden_states', 'external_cond', 'target_cond'],
        output_names=['pred_global_root'],
        opset_version=17,
        do_constant_folding=True,
        dynamic_axes={'hidden_states': {2: 'num_tokens'}, 'pred_global_root': {2: 'num_frames'},
                      'external_cond': {1: 'num_frames'}, 'target_cond': {1: 'num_frames'}},
    )
    print("✅ Root conv decoder exported")
    
    # Extract root backbone weights
    for name, param in root_backbone.named_parameters():
        fname = f"rootb_{name.replace('.', '_')}.npy"
        save_tensor(param, os.path.join(OUT_DIR, fname))
    print(f"✅ {sum(1 for _ in root_backbone.parameters())} root backbone params extracted")
    
    # ---- Save model metadata ----
    meta = {
        "vqvae": {
            "num_heads": 8,
            "code_dim": 256,
            "code_dim_per_head": 32,
            "num_codes_per_head": 10,
            "down_t": 2,
            "encoder_in_channels": vqvae.encoder.model[0].in_channels,
            "decoder_out_channels": vqvae.decoder.model[6].out_channels,
            "codebook_shape": list(vqvae.get_codebook().shape),
        },
        "pose_backbone": {
            "n_embd": pose_backbone._args['n_embd'],
            "n_head": pose_backbone._args['n_head'],
            "n_layers": pose_backbone._args['n_layers'],
            "num_pose_heads": pose_backbone.get_num_heads()[0],
            "num_codes_per_head": pose_backbone.get_num_codes(include_aug_tokens=False)[0],
            "num_frames_per_token": pose_backbone.get_num_frames_per_token(),
            "local_root_dim": pose_backbone._args.get('local_root_dim', 4),
            "local_pose_dim": pose_backbone._args.get('local_pose_dim', 304),
            "pose_feat_width": pose_backbone._args.get('pose_feat_width', 640),
            "root_feat_width": pose_backbone._args.get('root_feat_width', 256),
            "token_length_feat_width": pose_backbone._args.get('token_length_feat_width', 128),
        },
        "root_backbone": {
            "n_embd": root_backbone._args['n_embd'],
            "n_head": root_backbone._args['n_head'],
            "n_layers_shared": root_backbone._args['n_layers_shared'],
            "n_layers_root_token": root_backbone._args.get('n_layers_root_token', 0),
            "num_frames_per_token": root_backbone.get_num_frames_per_token(),
            "max_tokens": root_backbone._args['max_tokens'],
            "min_tokens": root_backbone._args['min_tokens'],
            "down_t": root_backbone._args['down_t'],
            "global_root_dim": root_backbone._args['global_root_dim'],
            "local_root_dim": root_backbone._args['local_root_dim'],
            "local_pose_dim": root_backbone._args.get('local_pose_dim', 329),
            "width": root_backbone._args.get('width', 512),
            "depth": root_backbone._args.get('depth', 4),
            "dilation_growth_rate": root_backbone._args.get('dilation_growth_rate', 3),
        }
    }
    
    meta_path = os.path.join(OUT_DIR, "motionbricks_meta.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"✅ Metadata saved to {meta_path}")
    
    # List outputs
    print(f"\nFiles in {OUT_DIR}:")
    for f in sorted(os.listdir(OUT_DIR)):
        fp = os.path.join(OUT_DIR, f)
        size = os.path.getsize(fp) if os.path.isfile(fp) else 0
        tag = "ONNX" if f.endswith('.onnx') else ("NPY" if f.endswith('.npy') else "")
        print(f"  [{tag}] {f}: {size:,} bytes")

if __name__ == '__main__':
    main()
