import pybullet as p
import numpy as np
import math

class ROVDynamics:
    def __init__(self, version="6-thruster", mass=11.5, buoyancy_factor=1.02, max_thrust=30.0):
        """
        ROV Dynamics Simulation Class.
        Uses headless PyBullet to calculate rigid-body physics.
        Supports switching configuration between "3-thruster" and "6-thruster".
        """
        self.mass = mass
        self.buoyancy_factor = buoyancy_factor  # > 1.0 means positively buoyant
        self.max_thrust = max_thrust
        self.version = version
        
        # Connect to PyBullet in DIRECT (headless) mode
        self.physics_client = p.connect(p.DIRECT)
        p.setGravity(0, 0, -9.81)
        
        # Center of Buoyancy offset relative to Center of Gravity (body frame)
        # Having CB above CG provides restoring torque (metacentric stability)
        self.cb_offset = np.array([0.0, 0.0, 0.08])
        
        # Hydrodynamic Drag Coefficients: [Linear, Quadratic]
        self.drag_linear = np.array([25.0, 35.0, 45.0])
        self.drag_quadratic = np.array([35.0, 45.0, 55.0])
        
        # Rotational Drag Coefficients: [Linear, Quadratic]
        self.drag_rot_linear = np.array([6.0, 8.0, 8.0])
        self.drag_rot_quadratic = np.array([10.0, 12.0, 12.0])
        
        # Create ROV body
        self.rov_id = None
        self.build_rov_body()
        
        # Initialize Thruster Layout
        self.setup_thruster_layout()
        
        # External SLAM position override flag
        self.use_external_slam = False
        self.external_pos = np.array([0.0, 0.0, 0.0])
        self.external_quat = np.array([0.0, 0.0, 0.0, 1.0])
        
    def build_rov_body(self):
        """Builds or rebuilds the PyBullet body based on the mass and layout."""
        if self.rov_id is not None:
            p.removeBody(self.rov_id)
            
        half_extents = [0.225, 0.17, 0.125]
        col_id = p.createCollisionShape(p.GEOM_BOX, halfExtents=half_extents)
        vis_id = p.createVisualShape(p.GEOM_BOX, halfExtents=half_extents, rgbaColor=[0.1, 0.15, 0.2, 1.0])
        
        ixx = (1.0/12.0) * self.mass * ( (2*half_extents[1])**2 + (2*half_extents[2])**2 )
        iyy = (1.0/12.0) * self.mass * ( (2*half_extents[0])**2 + (2*half_extents[2])**2 )
        izz = (1.0/12.0) * self.mass * ( (2*half_extents[0])**2 + (2*half_extents[1])**2 )
        
        self.rov_id = p.createMultiBody(
            baseMass=self.mass,
            baseCollisionShapeIndex=col_id,
            baseVisualShapeIndex=vis_id,
            basePosition=[0.0, 0.0, 0.0],
            baseOrientation=[0.0, 0.0, 0.0, 1.0]
        )
        
        p.changeDynamics(self.rov_id, -1, 
                         linearDamping=0.0, 
                         angularDamping=0.0,
                         localInertiaDiagonal=[ixx, iyy, izz])

    def setup_thruster_layout(self):
        """Sets up thrusters and TAM for 3-thruster vs 6-thruster configurations."""
        if self.version == "3-thruster":
            # 3-Thruster Layout: 2 Horizontal, 1 Vertical
            self.thrusters = [
                # T1: Port Horizontal (Forward)
                {"pos": [0.0, 0.15, 0.0], "dir": [1.0, 0.0, 0.0]},
                # T2: Starboard Horizontal (Forward)
                {"pos": [0.0, -0.15, 0.0], "dir": [1.0, 0.0, 0.0]},
                # T3: Vertical Center (Up)
                {"pos": [0.0, 0.0, 0.0], "dir": [0.0, 0.0, 1.0]}
            ]
        else:  # "6-thruster" (Standard vectored layout)
            self.thrusters = [
                # T1: Front-Right (Vectored Forward-Left)
                {"pos": [0.15, -0.15, 0.0], "dir": [0.707, 0.707, 0.0]},
                # T2: Front-Left (Vectored Forward-Right)
                {"pos": [0.15, 0.15, 0.0], "dir": [0.707, -0.707, 0.0]},
                # T3: Rear-Right (Vectored Backward-Left)
                {"pos": [-0.15, -0.15, 0.0], "dir": [-0.707, 0.707, 0.0]},
                # T4: Rear-Left (Vectored Backward-Right)
                {"pos": [-0.15, 0.15, 0.0], "dir": [-0.707, -0.707, 0.0]},
                # T5: Vertical Starboard (Up)
                {"pos": [0.0, -0.12, 0.05], "dir": [0.0, 0.0, 1.0]},
                # T6: Vertical Port (Up)
                {"pos": [0.0, 0.12, 0.05], "dir": [0.0, 0.0, 1.0]}
            ]
            
        num_thrusters = len(self.thrusters)
        self.TAM = np.zeros((6, num_thrusters))
        for i, t in enumerate(self.thrusters):
            pos = np.array(t["pos"])
            d = np.array(t["dir"])
            self.TAM[0:3, i] = d
            self.TAM[3:6, i] = np.cross(pos, d)
            
        self.TAM_pinv = np.linalg.pinv(self.TAM)
        self.thruster_inputs = np.zeros(num_thrusters)

    def change_configuration(self, version):
        """Changes the active configuration layout."""
        if version in ["3-thruster", "6-thruster"] and version != self.version:
            self.version = version
            self.build_rov_body()
            self.setup_thruster_layout()
            self.reset()

    def reset(self, position=[0.0, 0.0, 0.0], orientation=[0.0, 0.0, 0.0, 1.0]):
        """Resets the ROV pose and velocities."""
        p.resetBasePositionAndOrientation(self.rov_id, position, orientation)
        p.resetBaseVelocity(self.rov_id, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        self.thruster_inputs = np.zeros(len(self.thrusters))
        self.use_external_slam = False

    def set_external_pose(self, position, orientation_quat):
        """Overrides the physical model pose with coordinates from SLAM."""
        self.external_pos = np.array(position)
        self.external_quat = np.array(orientation_quat)
        self.use_external_slam = True
        
        # Teleport rigid body in PyBullet to stay in sync
        p.resetBasePositionAndOrientation(self.rov_id, position, orientation_quat)

    def set_control_input(self, surge=0.0, sway=0.0, heave=0.0, roll=0.0, pitch=0.0, yaw=0.0):
        """Computes and sets thruster speeds based on 6-DOF controls."""
        f_max_linear = 80.0
        t_max_rot = 20.0
        
        # Limit control inputs for 3-thruster configuration
        if self.version == "3-thruster":
            sway = 0.0
            roll = 0.0
            pitch = 0.0
            
        tau_des = np.array([
            surge * f_max_linear,
            sway * f_max_linear,
            heave * f_max_linear,
            roll * t_max_rot,
            pitch * t_max_rot,
            yaw * t_max_rot
        ])
        
        raw_inputs = self.TAM_pinv @ (tau_des)
        self.thruster_inputs = np.clip(raw_inputs, -1.0, 1.0)
        
    def get_thruster_outputs(self):
        """Returns active thruster outputs in percentage (0 to 100%)."""
        return np.round(np.abs(self.thruster_inputs) * 100.0).astype(int)
        
    def step(self, dt=1/240.0):
        """Steps the physics simulation forward."""
        # 1. Retrieve pose
        pos, quat = p.getBasePositionAndOrientation(self.rov_id)
        linear_vel_world, angular_vel_world = p.getBaseVelocity(self.rov_id)
        
        # 2. Coordinate transform World velocity -> Body velocity
        _, inv_quat = p.invertTransform([0, 0, 0], quat)
        linear_vel_body, _ = p.multiplyTransforms([0, 0, 0], inv_quat, linear_vel_world, [0, 0, 0, 1])
        angular_vel_body, _ = p.multiplyTransforms([0, 0, 0], inv_quat, angular_vel_world, [0, 0, 0, 1])
        
        v_b = np.array(linear_vel_body)
        w_b = np.array(angular_vel_body)
        
        # 3. Apply Buoyancy
        gravity_accel = 9.81
        buoyancy_force_val = self.mass * gravity_accel * self.buoyancy_factor
        buoyancy_force_world = [0.0, 0.0, buoyancy_force_val]
        
        cb_world, _ = p.multiplyTransforms(pos, quat, self.cb_offset, [0, 0, 0, 1])
        p.applyExternalForce(self.rov_id, -1, forceObj=buoyancy_force_world, posObj=cb_world, flags=p.WORLD_FRAME)
        
        # 4. Apply Hydrodynamic Drag (Linear + Quadratic)
        drag_force_body = - (self.drag_linear * v_b + self.drag_quadratic * v_b * np.abs(v_b))
        drag_torque_body = - (self.drag_rot_linear * w_b + self.drag_rot_quadratic * w_b * np.abs(w_b))
        
        p.applyExternalForce(self.rov_id, -1, forceObj=drag_force_body, posObj=[0.0, 0.0, 0.0], flags=p.LINK_FRAME)
        p.applyExternalTorque(self.rov_id, -1, torqueObj=drag_torque_body, flags=p.LINK_FRAME)
        
        # 5. Apply Active Thrusters
        for i, t in enumerate(self.thrusters):
            thrust_force = self.thruster_inputs[i] * self.max_thrust
            force_vector = np.array(t["dir"]) * thrust_force
            p.applyExternalForce(self.rov_id, -1, forceObj=force_vector, posObj=t["pos"], flags=p.LINK_FRAME)
            
        # 6. Step PyBullet simulation
        p.setTimeStep(dt)
        p.stepSimulation()
        
        # 7. Get new state
        if self.use_external_slam:
            # Override position with SLAM position if running in SLAM-feedback loop
            new_pos = self.external_pos
            new_quat = self.external_quat
        else:
            new_pos, new_quat = p.getBasePositionAndOrientation(self.rov_id)
            
        new_lin_vel, new_ang_vel = p.getBaseVelocity(self.rov_id)
        
        euler = p.getEulerFromQuaternion(new_quat)
        roll_deg = math.degrees(euler[0])
        pitch_deg = math.degrees(euler[1])
        yaw_deg = math.degrees(euler[2])
        heading = (yaw_deg + 360.0) % 360.0
        
        return {
            "position": np.array(new_pos),
            "orientation_quat": np.array(new_quat),
            "linear_velocity": np.array(new_lin_vel),
            "angular_velocity": np.array(new_ang_vel),
            "heading": heading,
            "pitch": pitch_deg,
            "roll": roll_deg,
            "thruster_outputs": self.get_thruster_outputs()
        }

    def close(self):
        """Disconnects PyBullet physics client."""
        try:
            p.disconnect(self.physics_client)
        except Exception:
            pass
