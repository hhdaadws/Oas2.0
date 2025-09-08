"""
执行器使用示例
"""
import asyncio
from src.app.modules.executor.game_executor import GameExecutor


async def main():
    """主函数示例"""
    # 初始化执行器（使用ADB截图）
    executor = GameExecutor(
        adb_addr="127.0.0.1:16384",  # 对应实例0
        instance_id=0,
        use_ipc=False  # 使用ADB截图
    )
    
    try:
        # 1. 初始化执行器
        print("初始化执行器...")
        if not await executor.initialize():
            print("执行器初始化失败")
            return
        
        # 2. 截图测试
        print("执行截图测试...")
        screenshot_path = "screenshots/test_screenshot.png"
        await executor.take_screenshot(save_path=screenshot_path)
        print(f"截图已保存: {screenshot_path}")
        
        # 3. 检查阴阳师状态
        print("检查阴阳师运行状态...")
        if await executor.is_onmyoji_running():
            print("阴阳师已在运行")
        else:
            print("阴阳师未运行，尝试启动...")
            
        # 4. 启动阴阳师
        print("启动阴阳师游戏...")
        if await executor.start_onmyoji_game():
            print("阴阳师启动成功")
        else:
            print("阴阳师启动失败")
        
        # 5. 关闭阴阳师示例
        print("关闭阴阳师游戏...")
        if await executor.stop_onmyoji_game():
            print("阴阳师关闭成功")
        
        # 6. 重启阴阳师示例  
        print("重启阴阳师游戏...")
        if await executor.restart_onmyoji_game():
            print("阴阳师重启成功")
        
        # 4. 模板匹配示例
        print("查找并点击模板...")
        if await executor.find_and_click_template("some_button.png"):
            print("模板点击成功")
        else:
            print("未找到模板或点击失败")
        
        # 5. 在区域内随机点击
        print("在指定区域随机点击...")
        if await executor.click_random_in_area(100, 100, 200, 100):
            print("随机点击成功")
        
        # 6. 等待特定界面出现
        print("等待特定界面...")
        result = await executor.wait_for_template("target_screen.png", timeout=10)
        if result:
            print(f"界面出现，位置: ({result.center_x}, {result.center_y})")
        else:
            print("等待界面超时")
        
    finally:
        # 清理资源
        executor.cleanup()


# 使用示例：查找小图并随机点击
async def find_and_click_example():
    """查找小图并随机点击的示例"""
    executor = GameExecutor("127.0.0.1:16384", 0)
    
    try:
        if await executor.initialize():
            # 在大图中查找小图，然后在小图区域内随机点击
            templates_to_find = [
                "button1.png",
                "button2.png", 
                "icon1.png"
            ]
            
            # 方法1: 查找最佳匹配并点击
            if await executor.find_templates_and_click_best(templates_to_find):
                print("找到并点击了最佳匹配的模板")
            
            # 方法2: 逐个查找并点击
            for template in templates_to_find:
                if await executor.find_and_click_template(template, use_random=True):
                    print(f"找到并点击了: {template}")
                    break
            
    finally:
        executor.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())