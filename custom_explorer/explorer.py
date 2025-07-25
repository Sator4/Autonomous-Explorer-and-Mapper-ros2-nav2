import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
import numpy as np
from matplotlib import pyplot as plt


class ExplorerNode(Node):
	def __init__(self):
		super().__init__('explorer')
		self.get_logger().info("Explorer Node Started")

		# Subscriber to the map topic
		self.map_sub = self.create_subscription(
			OccupancyGrid, '/map', self.map_callback, 10)
		
		# Subscriber to the costmap topic
		self.costmap_sub = self.create_subscription(
			OccupancyGrid, '/global_costmap/costmap', self.costmap_callback, 10)

		# Action client for navigation
		self.nav_to_pose_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

		# Visited frontiers set
		self.visited_frontiers = set()

		# Map and position data
		self.map_data = None
		self.costmap_data = None
		self.robot_position = (0, 0)  # Placeholder, update from localization

		# Timer for periodic exploration
		self.timer = self.create_timer(5.0, self.explore)

	def map_callback(self, msg):
		self.map_data = msg
		self.get_logger().info("Map received")
		
	def costmap_callback(self, msg):
		self.costmap_data = msg
		self.get_logger().info("Costmap received")

	def navigate_to(self, x, y):
		"""
		Send navigation goal to Nav2.
		"""
		goal_msg = PoseStamped()
		goal_msg.header.frame_id = 'map'
		goal_msg.header.stamp = self.get_clock().now().to_msg()
		goal_msg.pose.position.x = x
		goal_msg.pose.position.y = y

		nav_goal = NavigateToPose.Goal()
		nav_goal.pose = goal_msg

		self.get_logger().info(f"Navigating to goal: x={x}, y={y}")

		# Wait for the action server
		self.nav_to_pose_client.wait_for_server()

		# Send the goal and register a callback for the result
		send_goal_future = self.nav_to_pose_client.send_goal_async(nav_goal)
		send_goal_future.add_done_callback(self.goal_response_callback)

	def goal_response_callback(self, future):
		"""
		Handle the goal response and attach a callback to the result.
		"""
		goal_handle = future.result()

		if not goal_handle.accepted:
			self.get_logger().warning("Goal rejected!")
			return

		self.get_logger().info("Goal accepted")
		result_future = goal_handle.get_result_async()
		result_future.add_done_callback(self.navigation_complete_callback)

	def navigation_complete_callback(self, future):
		"""
		Callback to handle the result of the navigation action.
		"""
		try:
			result = future.result().result
			self.get_logger().info(f"Navigation completed with result: {result}")
		except Exception as e:
			self.get_logger().error(f"Navigation failed: {e}")

	def find_frontiers(self, map_array, costmap_array):
		"""
		Detect frontiers in the occupancy grid map.
		"""
		frontiers = []
		rows, cols = map_array.shape
		robot_row, robot_col = self.robot_position

		# Iterate through each cell in the map
		for r in range(1, rows - 1):
			for c in range(1, cols - 1):
				distance = np.sqrt((robot_row - r)**2 + (robot_col - c)**2)
				if map_array[r, c] == 0: # or map_array[r, c] == -1 and distance <= 40:  # Free cell
					# Check if any neighbors are unknown
					neighbors = map_array[r-1:r+2, c-1:c+2].flatten()
					if -1 in neighbors:
						frontiers.append((r, c, costmap_array[r, c]))

		self.get_logger().info(f"Found {len(frontiers)} frontiers")
		# self.get_logger().info(f"Map: {map_array}")
		# self.get_logger().info(f"Costmap: {costmap_array}")
		# self.get_logger().info(f"Frontiers: {frontiers}")
		# plt.imsave('/home/sator/ros2_program/images/map.png', map_array, cmap='gray')
		# plt.imsave('/home/sator/ros2_program/images/costmap.png', costmap_array, cmap='gray')
		return frontiers

	def choose_frontier(self, frontiers):
		"""
		Choose the closest frontier to the robot.
		"""
		
		# coef = costcoef * 1 / (cost + 2) + distcoef * distance + shiftcoef * 1 / (dx + 1) * 1 / (dy + 1) -> min

		robot_row, robot_col = self.robot_position
		min_distance = float('inf')
		chosen_frontier = None
		
		# costcoef, distcoef, shiftcoef = 0.05, 0.002, 30
		coef_sum = float('inf')


		for frontier in frontiers:
			if frontier in self.visited_frontiers:
				continue
			
			distance = np.sqrt((robot_row - frontier[0])**2 + (robot_col - frontier[1])**2)
			# dx, dy = np.abs(robot_col - frontier[1]), np.abs(robot_row - frontier[0])
			# cost_coef = costcoef * frontier[2]
			# dist_coef = distcoef * distance
			# shift_coef = shiftcoef / ((dx + 2) * (dy + 2))**0.5
			# self.get_logger().info(f"cost_coef: {np.round(cost_coef, 4)}({frontier[2]}), dist_coef: {np.round(dist_coef, 4)}({distance}), shift_coef: {np.round(shift_coef, 4)}(dx: {dx}, dy: {dy})")

			if distance < min_distance and (not chosen_frontier) or (chosen_frontier and frontier[2] <= chosen_frontier[2]):
			# if cost_coef + dist_coef + shift_coef < coef_sum:
				min_distance = distance
				# coef_sum = cost_coef + dist_coef + shift_coef
				chosen_frontier = frontier

		if chosen_frontier:
			self.visited_frontiers.add(chosen_frontier)

			# distance = np.sqrt((robot_row - chosen_frontier[0])**2 + (robot_col - chosen_frontier[1])**2)
			# dx, dy = np.abs(robot_col - chosen_frontier[1]), np.abs(robot_row - chosen_frontier[0])
			# cost_coef = costcoef * chosen_frontier[2]
			# dist_coef = distcoef * distance
			# shift_coef = shiftcoef / ((dx + 2) * (dy + 2))**0.5
			# coef_sum = cost_coef + dist_coef + shift_coef
			# cost_coef = cost_coef / coef_sum * 100
			# dist_coef = dist_coef / coef_sum * 100
			# shift_coef = shift_coef / coef_sum * 100
			self.get_logger().info(f"Chosen chosen_frontier: {chosen_frontier}")
			# self.get_logger().info(f"cost_coef: {np.round(cost_coef, 4)}% ({chosen_frontier[2]}), dist_coef: {np.round(dist_coef, 4)}% ({np.round(distance, 4)}), shift_coef: {np.round(shift_coef, 4)}% (dx: {dx}, dy: {dy})")
		else:
			self.get_logger().warning("No valid frontier found")

		# exit()
		return chosen_frontier

	def explore(self):
		if self.map_data is None:
			self.get_logger().warning("No map data available")
			return
		
		if self.costmap_data is None:
			self.get_logger().warning("No costmap data available")
			return

		# Convert map to numpy array
		map_array = np.array(self.map_data.data).reshape(
			(self.map_data.info.height, self.map_data.info.width))
		
		costmap_array = np.array(self.costmap_data.data).reshape(
			(self.costmap_data.info.height, self.costmap_data.info.width))

		# Detect frontiers
		frontiers = self.find_frontiers(map_array, costmap_array)

		if not frontiers:
			self.get_logger().info("No frontiers found. Exploration complete!")
			self.shutdown_robot()
			return

		# Choose the closest frontier
		chosen_frontier = self.choose_frontier(frontiers)

		if not chosen_frontier:
			self.get_logger().warning("No frontiers to explore")
			return

		# Convert the chosen frontier to world coordinates
		goal_x = chosen_frontier[1] * self.map_data.info.resolution + self.map_data.info.origin.position.x
		goal_y = chosen_frontier[0] * self.map_data.info.resolution + self.map_data.info.origin.position.y

		# Navigate to the chosen frontier
		self.navigate_to(goal_x, goal_y)

	def shudown_robot(self):    
		self.get_logger().info("Shutting down robot exploration")
		self.destroy_node()
		rclpy.shutdown()
		return


def main(args=None):
	rclpy.init(args=args)
	explorer_node = ExplorerNode()

	try:
		explorer_node.get_logger().info("Starting exploration...")
		rclpy.spin(explorer_node)
	except KeyboardInterrupt:
		explorer_node.get_logger().info("Exploration stopped by user")
	finally:
		explorer_node.destroy_node()
		rclpy.shutdown()
