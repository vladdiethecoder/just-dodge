//! Integer-only projection from a quantized 6D rotation basis to one hinge angle.
//!
//! This is a representation primitive, not a motor controller or physics step.

const Q15_ONE: i64 = i16::MAX as i64;
const Q30_ONE: i64 = 1_i64 << 30;
const PI_MICRORADIANS: i32 = 3_141_593;
const CORDIC_ATAN_MICRORADIANS: [i32; 21] = [
    785_398, 463_648, 244_979, 124_355, 62_419, 31_240, 15_624, 7_812, 3_906, 1_953, 977, 488, 244,
    122, 61, 31, 15, 8, 4, 2, 1,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HingeProjectionError {
    InvalidRotationBasis,
    InvalidHingeAxis,
}

pub fn project_hinge_angle_microradians(
    rotation_6d_q15: [i16; 6],
    hinge_axis_q30: [i32; 3],
) -> Result<i32, HingeProjectionError> {
    if !valid_rotation_basis(rotation_6d_q15) {
        return Err(HingeProjectionError::InvalidRotationBasis);
    }
    let (sine, cosine) = match hinge_axis_q30 {
        [x, 0, 0] if i64::from(x).abs() == Q30_ONE => (
            i32::from(rotation_6d_q15[5]) * x.signum(),
            i32::from(rotation_6d_q15[4]),
        ),
        [0, y, 0] if i64::from(y).abs() == Q30_ONE => (
            -i32::from(rotation_6d_q15[2]) * y.signum(),
            i32::from(rotation_6d_q15[0]),
        ),
        [0, 0, z] if i64::from(z).abs() == Q30_ONE => (
            i32::from(rotation_6d_q15[1]) * z.signum(),
            i32::from(rotation_6d_q15[0]),
        ),
        _ => return Err(HingeProjectionError::InvalidHingeAxis),
    };
    Ok(cordic_angle_microradians(sine, cosine))
}

fn valid_rotation_basis(rotation: [i16; 6]) -> bool {
    let first = rotation[..3].iter().copied().map(i64::from);
    let second = rotation[3..].iter().copied().map(i64::from);
    let norm_first: i64 = first.clone().map(|value| value * value).sum();
    let norm_second: i64 = second.clone().map(|value| value * value).sum();
    let dot: i64 = first.zip(second).map(|(a, b)| a * b).sum();
    let unit_squared = Q15_ONE * Q15_ONE;
    let minimum_norm = unit_squared * 3 / 4;
    let maximum_norm = unit_squared * 5 / 4;
    (minimum_norm..=maximum_norm).contains(&norm_first)
        && (minimum_norm..=maximum_norm).contains(&norm_second)
        && dot.abs() <= unit_squared / 8
}

fn cordic_angle_microradians(y: i32, x: i32) -> i32 {
    if x == 0 && y == 0 {
        return 0;
    }
    let mut x = i64::from(x);
    let mut y = i64::from(y);
    let mut angle = 0_i64;
    if x < 0 {
        angle = if y >= 0 {
            i64::from(PI_MICRORADIANS)
        } else {
            -i64::from(PI_MICRORADIANS)
        };
        x = -x;
        y = -y;
    }
    for (shift, step) in CORDIC_ATAN_MICRORADIANS.iter().enumerate() {
        if y > 0 {
            let next_x = x + (y >> shift);
            let next_y = y - (x >> shift);
            x = next_x;
            y = next_y;
            angle += i64::from(*step);
        } else if y < 0 {
            let next_x = x - (y >> shift);
            let next_y = y + (x >> shift);
            x = next_x;
            y = next_y;
            angle -= i64::from(*step);
        } else {
            break;
        }
    }
    i32::try_from(angle.clamp(-i64::from(PI_MICRORADIANS), i64::from(PI_MICRORADIANS))).unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    const COS_HALF_Q15: i16 = 28_756;
    const SIN_HALF_Q15: i16 = 15_709;
    const X_AXIS_Q30: [i32; 3] = [1 << 30, 0, 0];
    const Y_AXIS_Q30: [i32; 3] = [0, 1 << 30, 0];
    const Z_AXIS_Q30: [i32; 3] = [0, 0, 1 << 30];

    fn assert_half_radian(actual: i32, sign: i32) {
        assert!((actual - sign * 500_000).abs() <= 100, "{actual}");
    }

    #[test]
    fn signed_half_radian_is_recovered_on_every_axis() {
        let x = [i16::MAX, 0, 0, 0, COS_HALF_Q15, SIN_HALF_Q15];
        let y = [COS_HALF_Q15, 0, -SIN_HALF_Q15, 0, i16::MAX, 0];
        let z = [
            COS_HALF_Q15,
            SIN_HALF_Q15,
            0,
            -SIN_HALF_Q15,
            COS_HALF_Q15,
            0,
        ];
        let negative_z = [
            COS_HALF_Q15,
            -SIN_HALF_Q15,
            0,
            SIN_HALF_Q15,
            COS_HALF_Q15,
            0,
        ];
        assert_half_radian(project_hinge_angle_microradians(x, X_AXIS_Q30).unwrap(), 1);
        assert_half_radian(project_hinge_angle_microradians(y, Y_AXIS_Q30).unwrap(), 1);
        assert_half_radian(project_hinge_angle_microradians(z, Z_AXIS_Q30).unwrap(), 1);
        assert_half_radian(
            project_hinge_angle_microradians(negative_z, Z_AXIS_Q30).unwrap(),
            -1,
        );
    }

    #[test]
    fn pi_quadrants_and_negative_axes_are_deterministic() {
        let x_pi = [i16::MAX, 0, 0, 0, -i16::MAX, 0];
        let positive = project_hinge_angle_microradians(x_pi, X_AXIS_Q30).unwrap();
        let negative = project_hinge_angle_microradians(x_pi, [-1 << 30, 0, 0]).unwrap();
        assert_eq!(positive, PI_MICRORADIANS);
        assert_eq!(negative, PI_MICRORADIANS);
    }

    #[test]
    fn identity_and_off_axis_components_project_to_zero() {
        let identity = [i16::MAX, 0, 0, 0, i16::MAX, 0];
        let z_half = [
            COS_HALF_Q15,
            SIN_HALF_Q15,
            0,
            -SIN_HALF_Q15,
            COS_HALF_Q15,
            0,
        ];
        assert_eq!(
            project_hinge_angle_microradians(identity, Y_AXIS_Q30),
            Ok(0)
        );
        assert_eq!(project_hinge_angle_microradians(z_half, X_AXIS_Q30), Ok(0));
    }

    #[test]
    fn malformed_basis_and_axis_fail_closed() {
        assert_eq!(
            project_hinge_angle_microradians([0; 6], X_AXIS_Q30),
            Err(HingeProjectionError::InvalidRotationBasis)
        );
        assert_eq!(
            project_hinge_angle_microradians([i16::MAX, 0, 0, 0, i16::MAX, 0], [1, 1, 0]),
            Err(HingeProjectionError::InvalidHingeAxis)
        );
    }
}
