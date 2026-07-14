---
license: other
license_name: nvidia-open-model-agreement
license_link: >-
  https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement
library_name: ardy
tags:
  - nvidia
  - ardy
  - rigplay
---

# ARDY: Autoregressive Diffusion with Hybrid Representation for Interactive Human Motion Generation

**[Paper](https://research.nvidia.com/labs/sil/projects/ardy/assets/ardy_paper.pdf), [Project Page](https://research.nvidia.com/labs/sil/projects/ardy/)**

## Description:
ARDY is an autoregressive diffusion model designed for interactive motion generation, supporting online text prompting and flexible long-horizon kinematic constraints (root paths/waypoints, full-body keyframes, and sparse joint positions/rotations) with real-time responsiveness.

ARDY-G1-RP-25FPS-Horizon52 was developed by NVIDIA as a part of the ARDY project. It was trained on the Bones Rigplay 1 dataset with the 34-joint Unitree G1 robot skeleton at 25 fps. See [below](#model-versions) for other model variants.

This model is ready for commercial or non-commercial use.


### License/Terms of Use:
Use of this model is governed by the [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/)
### Deployment Geography:
Global

### Use Case:
Developers and researchers with any level of animation experience can use ARDY to generate controllable humanoid motions in their real-time applications. This could include motion planning for humanoid robots, character movement in digital twin and industrial simulations, digital human motion for synthetic data, and animations for games and other interactive applications.


### Release Date:
**HuggingFace:** 07/10/2026 via [HuggingFace](https://huggingface.co/nvidia/Ardy-G1-RP-25FPS-Horizon52)



## Reference:
[ARDY: Autoregressive Diffusion with Hybrid Representation for Interactive Human Motion Generation](https://research.nvidia.com/labs/sil/projects/ardy/)

## Model Architecture:
**Architecture Type:** Diffusion Model <br>
**Network Architecture:** Novel Two-Stage Transformer  <br>
**Number of model parameters:** 326 M

## Input:
**Input Type(s):** Text, Other: Pose Constraints, History Poses  <br>
**Input Format(s):** String, Tensor  <br>
**Input Parameters:** One-Dimensional (1D), N-Dimensional (ND) <br>
**Other Properties Related to Input:** History pose duration is max 8 sec.


## Output:
**Output Type(s):** Other: Pose Sequence  <br>
**Output Format:** Tensor   <br>
**Output Parameters:** N-Dimensional (ND) <br>
**Other Properties Related to Output:** Pose sequence contains global root translation and joint rotations. Output poses have max duration of 8 sec.


Our AI models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.

## Software Integration:
**Runtime Engines:** PyTorch <br>
**Supported Hardware Microarchitecture Compatibility:**
* NVIDIA Ampere
* NVIDIA Blackwell
* NVIDIA Hopper

**Supported Operating System(s):** Linux

The integration of foundation and fine-tuned models into AI systems requires additional testing using use-case-specific data to ensure safe and effective deployment. Following the V-model methodology, iterative testing and validation at both unit and system levels are essential to mitigate risks, meet technical and functional requirements, and ensure compliance with safety and ethical standards before deployment.


## Model Versions:
* [ARDY-Core-RP-20FPS-Horizon40](https://huggingface.co/nvidia/ARDY-Core-RP-20FPS-Horizon40): 27-joint "core" skeleton at 20 fps, 40 frame generation horizon
* [ARDY-Core-RP-20FPS-Horizon8](https://huggingface.co/nvidia/ARDY-Core-RP-20FPS-Horizon8): 27-joint "core" skeleton at 20 fps, 8 frame generation horizon
* [ARDY-G1-RP-25FPS-Horizon52](https://huggingface.co/nvidia/ARDY-G1-RP-25FPS-Horizon52): 34-joint Unitree G1 robot skeleton at 25 fps, 52 frame generation horizon
* [ARDY-G1-RP-25FPS-Horizon8](https://huggingface.co/nvidia/ARDY-G1-RP-25FPS-Horizon8): 34-joint Unitree G1 robot skeleton at 25 fps, 8 frame generation horizon

This repo corresponds to the ARDY-G1-RP-25FPS-Horizon52 model variant.
Please refer to the [codebase](https://github.com/nv-tlabs/ardy) for installation and usage instructions.

## Training, Testing, and Evaluation Datasets:

The model was trained and evaluated using the [Bones Rigplay 1 dataset](https://bones.studio/datasets).

## Training Dataset:

**Data Modality:**
* Text
* Other: Human Motion Capture


**Text Training Data Size:** Less than a Billion Tokens  <br>
**Other Training Data Size:** 630 hours of human motion captures <br>
**Data Collection Method by dataset:** Automatic/Sensors  <br>
**Labeling Method by dataset:** Hybrid: Automated/Human  <br>
**Properties:** Contains optical motion capture data with corresponding text descriptions covering a diverse range of behaviors such as locomotion, everyday activities, and gestures. Motions are clipped to 10 sec long and resampled to the desired FPS for training. An LLM is used to augment the dataset with diverse paraphrases of text labels.

### Testing Dataset:

**Data Collection Method by dataset:** Automatic/Sensors  <br>
**Labeling Method by dataset:** Hybrid: Automated/Human  <br>
**Properties:** 70 hours of motion data held out from training. The test split contains motions from content categories not seen in training.

### Evaluation Dataset:

**Benchmark Score:** See [codebase](https://github.com/nv-tlabs/ardy) for evaluation results. <br>
**Data Collection Method by dataset:** Automatic/Sensors  <br>
**Labeling Method by dataset:** Hybrid: Automated/Human  <br>
**Properties:** Same as test dataset.



## Inference:
**Acceleration Engine:** TensorRT <br>
**Test Hardware:**
* NVIDIA A100
* NVIDIA RTX 4090


## Ethical Considerations:
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. Developers should work with their internal model team to ensure this model meets requirements for the relevant industry and use case and addresses unforeseen product misuse.

For more detailed information on ethical considerations for this model, please see the Model Card++ Bias, Explainability, Safety & Security, and Privacy Subcards below. <br>

Please report model quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/).  <br>


# Bias
Field                                                                                               |  Response
:---------------------------------------------------------------------------------------------------|:---------------
Participation considerations from adversely impacted groups [protected classes](https://www.senate.ca.gov/content/protected-classes) in model design and testing:  |  None
Measures taken to mitigate against unwanted bias:                                                   |  None
Bias Metric (If Measured):                                                   |   N/A

# Explainability
Field                                                                                                  |  Response
:------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------
Intended Task/Domain:                                                                                       |  Robotics, Animation
Model Type:                                                                                            |  Diffusion Model
Intended Users:                                                                                        |  Developers and researchers with any level of animation experience can use ARDY to generate controllable humanoid motions in their real-time applications, such as motion planning for humanoid robots, character movement in digital twin and industrial simulations, digital human motion for synthetic data, and animations for games and other interactive applications.
Output:                                                                                                |  Types: Other: Pose Sequence. Formats: Tensor
Describe how the model works:                                                                          |  ARDY is an autoregressive diffusion model designed for interactive motion generation, supporting online text prompting and flexible long-horizon kinematic constraints (root paths/waypoints, full-body keyframes, and sparse joint positions/rotations) with real-time responsiveness.
Name the adversely impacted groups this has been tested to deliver comparable outcomes regardless of:  |  Not Applicable
Technical Limitations and Mitigation:                                                                  |  Generated motions may include artifacts like foot skating where feet slide unnaturally when they should be in static contact with the ground. The motion does not always follow the given text prompt, and the model does not know how to perform certain types of actions (e.g., the model is best at locomotion, gestures, combat, dancing, and everyday activities). Each trained model currently outputs motion for a single character skeleton. The model is designed to output realistic human motions, so it cannot create cartoon motions or non-physically plausible motions. The model is not aware of objects in the scene around a character.
Verified to have met prescribed NVIDIA quality standards:                          |  Yes
Performance Metrics:                                                                                   |  Pose Constraint Accuracy (joint distance error), Motion Quality (foot-skating error, FID, latent similarity), Text-Following Accuracy (R-precision, latent similarity)
Potential Known Risks:                                                                                 |  The model may output body motions that inadvertently reflect stereotypes related to age, gender, or physical characteristics. To mitigate this, prompts should describe actions in neutral, physical terms (e.g., “A person walks slowly with shuffled steps”) rather than relying on demographic adjectives.
Licensing:                                                                                |  Use of this model is governed by the [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/)

# Safety and Security
Field                                               |  Response
:---------------------------------------------------|:----------------------------------
Model Application Field(s):                               |  Human Motion Generation
Describe the life critical impact (if present).   |  Not Applicable
Use Case Restrictions:                              |  Use of this model is governed by the [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/)
Model and dataset restrictions:            |  The Principle of least privilege (PoLP) is applied limiting access for dataset generation and model development. Restrictions enforce dataset access during training, and dataset license constraints adhered to.

# Privacy
Field                                                                                                                              |  Response
:----------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------
Generatable or reverse engineerable personal data?                                                     |  No
Personal data used to create this model?                      |  No
Was consent obtained for any personal data used?                                                                                   |  Not Applicable
How often is dataset reviewed?                                                                                                     |  Before Every Release
Was data from user interactions with the AI model used to train the model?                           |  No
Is there provenance for all datasets used in training?                                                                             |  Yes
Does data labeling (annotation, metadata) comply with privacy laws?                                                                |  Yes
Is data compliant with data subject requests for data correction or removal, if such a request was made? |  Yes
Applicable Privacy Policy                                                                                                          | https://www.nvidia.com/en-us/about-nvidia/privacy-policy/
