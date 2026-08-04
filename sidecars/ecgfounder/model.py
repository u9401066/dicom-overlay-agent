"""Pinned ECGFounder 12-lead network architecture.

Adapted from ``net1d.py`` in PKUDigitalHealth/ECGFounder revision
``04edac702b61c91face519774ddcc0cd712fef23`` (MIT license). Attribute names
are intentionally kept compatible with the published checkpoint state dict.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as functional


class MyConv1dPadSame(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        stride: int,
        groups: int = 1,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.groups = groups
        self.conv = nn.Conv1d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            groups=groups,
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        input_length = value.shape[-1]
        output_length = (input_length + self.stride - 1) // self.stride
        padding = max(
            0,
            (output_length - 1) * self.stride + self.kernel_size - input_length,
        )
        left = padding // 2
        return self.conv(functional.pad(value, (left, padding - left)))


class MyMaxPool1dPadSame(nn.Module):
    def __init__(self, kernel_size: int) -> None:
        super().__init__()
        self.kernel_size = kernel_size
        self.max_pool = nn.MaxPool1d(kernel_size=kernel_size)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        padding = max(0, self.kernel_size - 1)
        left = padding // 2
        return self.max_pool(functional.pad(value, (left, padding - left)))


class Swish(nn.Module):
    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return value * torch.sigmoid(value)


class BasicBlock(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        ratio: int,
        kernel_size: int,
        stride: int,
        groups: int,
        downsample: bool,
        *,
        is_first_block: bool = False,
        use_bn: bool = True,
        use_do: bool = True,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.ratio = ratio
        self.kernel_size = kernel_size
        self.groups = groups
        self.downsample = downsample
        self.stride = stride if downsample else 1
        self.is_first_block = is_first_block
        self.use_bn = use_bn
        self.use_do = use_do
        self.middle_channels = int(out_channels * ratio)

        self.bn1 = nn.BatchNorm1d(in_channels)
        self.activation1 = Swish()
        self.do1 = nn.Dropout(p=0.5)
        self.conv1 = MyConv1dPadSame(
            in_channels,
            self.middle_channels,
            kernel_size=1,
            stride=1,
        )
        self.bn2 = nn.BatchNorm1d(self.middle_channels)
        self.activation2 = Swish()
        self.do2 = nn.Dropout(p=0.5)
        self.conv2 = MyConv1dPadSame(
            self.middle_channels,
            self.middle_channels,
            kernel_size=kernel_size,
            stride=self.stride,
            groups=groups,
        )
        self.bn3 = nn.BatchNorm1d(self.middle_channels)
        self.activation3 = Swish()
        self.do3 = nn.Dropout(p=0.5)
        self.conv3 = MyConv1dPadSame(
            self.middle_channels,
            out_channels,
            kernel_size=1,
            stride=1,
        )

        self.se_fc1 = nn.Linear(out_channels, out_channels // 2)
        self.se_fc2 = nn.Linear(out_channels // 2, out_channels)
        self.se_activation = Swish()
        if downsample:
            self.max_pool = MyMaxPool1dPadSame(kernel_size=self.stride)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        identity = value
        output = value
        if not self.is_first_block:
            if self.use_bn:
                output = self.bn1(output)
            output = self.activation1(output)
            if self.use_do:
                output = self.do1(output)
        output = self.conv1(output)

        if self.use_bn:
            output = self.bn2(output)
        output = self.activation2(output)
        if self.use_do:
            output = self.do2(output)
        output = self.conv2(output)

        if self.use_bn:
            output = self.bn3(output)
        output = self.activation3(output)
        if self.use_do:
            output = self.do3(output)
        output = self.conv3(output)

        excitation = output.mean(-1)
        excitation = self.se_fc1(excitation)
        excitation = self.se_activation(excitation)
        excitation = torch.sigmoid(self.se_fc2(excitation))
        output = torch.einsum("abc,ab->abc", output, excitation)

        if self.downsample:
            identity = self.max_pool(identity)
        if self.out_channels != self.in_channels:
            identity = identity.transpose(-1, -2)
            left = (self.out_channels - self.in_channels) // 2
            right = self.out_channels - self.in_channels - left
            identity = functional.pad(identity, (left, right))
            identity = identity.transpose(-1, -2)
        return output + identity


class BasicStage(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        ratio: int,
        kernel_size: int,
        stride: int,
        groups: int,
        i_stage: int,
        m_blocks: int,
        *,
        use_bn: bool = True,
        use_do: bool = True,
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.ratio = ratio
        self.kernel_size = kernel_size
        self.groups = groups
        self.i_stage = i_stage
        self.m_blocks = m_blocks
        self.use_bn = use_bn
        self.use_do = use_do
        self.verbose = verbose
        self.block_list = nn.ModuleList()
        for block_index in range(m_blocks):
            block_in_channels = in_channels if block_index == 0 else out_channels
            self.block_list.append(
                BasicBlock(
                    in_channels=block_in_channels,
                    out_channels=out_channels,
                    ratio=ratio,
                    kernel_size=kernel_size,
                    stride=stride if block_index == 0 else 1,
                    groups=groups,
                    downsample=block_index == 0,
                    is_first_block=i_stage == 0 and block_index == 0,
                    use_bn=use_bn,
                    use_do=use_do,
                )
            )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        output = value
        for block in self.block_list:
            output = block(output)
        return output


class Net1D(nn.Module):
    def __init__(
        self,
        in_channels: int,
        base_filters: int,
        ratio: int,
        filter_list: list[int],
        m_blocks_list: list[int],
        kernel_size: int,
        stride: int,
        groups_width: int,
        n_classes: int,
        *,
        use_bn: bool = True,
        use_do: bool = True,
        return_features: bool = False,
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.base_filters = base_filters
        self.ratio = ratio
        self.filter_list = filter_list
        self.m_blocks_list = m_blocks_list
        self.kernel_size = kernel_size
        self.stride = stride
        self.groups_width = groups_width
        self.n_stages = len(filter_list)
        self.n_classes = n_classes
        self.use_bn = use_bn
        self.use_do = use_do
        self.return_features = return_features
        self.verbose = verbose

        self.first_conv = MyConv1dPadSame(
            in_channels,
            base_filters,
            kernel_size=kernel_size,
            stride=2,
        )
        self.first_bn = nn.BatchNorm1d(base_filters)
        self.first_activation = Swish()
        self.stage_list = nn.ModuleList()
        stage_in_channels = base_filters
        for stage_index, out_channels in enumerate(filter_list):
            self.stage_list.append(
                BasicStage(
                    in_channels=stage_in_channels,
                    out_channels=out_channels,
                    ratio=ratio,
                    kernel_size=kernel_size,
                    stride=stride,
                    groups=out_channels // groups_width,
                    i_stage=stage_index,
                    m_blocks=m_blocks_list[stage_index],
                    use_bn=use_bn,
                    use_do=use_do,
                    verbose=verbose,
                )
            )
            stage_in_channels = out_channels
        self.dense = nn.Linear(stage_in_channels, n_classes)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        output = self.first_conv(value)
        if self.use_bn:
            output = self.first_bn(output)
        output = self.first_activation(output)
        for stage in self.stage_list:
            output = stage(output)
        deep_features = output.mean(-1)
        prediction = self.dense(deep_features)
        if self.return_features:
            return prediction, deep_features
        return prediction


def build_ecgfounder_12lead_model() -> Net1D:
    """Construct the exact network used by the official PTB-XL validator."""

    return Net1D(
        in_channels=12,
        base_filters=64,
        ratio=1,
        filter_list=[64, 160, 160, 400, 400, 1024, 1024],
        m_blocks_list=[2, 2, 2, 3, 3, 4, 4],
        kernel_size=16,
        stride=2,
        groups_width=16,
        use_bn=False,
        use_do=False,
        n_classes=150,
    )
