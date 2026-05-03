"""ML training pipeline for pickleball rally detection.

Trains an audio classifier to detect active rally segments in pickleball
match videos. Uses mel spectrogram windows with a CNN classifier.

Modules:
    config: Hyperparameters and path configuration
    dataset: Audio extraction, spectrogram computation, PyTorch Dataset
    model: CNN classifier architecture
    train: Training loop with validation
    predict: Inference on new videos with post-processing
"""
