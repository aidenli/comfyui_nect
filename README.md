# ComfyUI Nect 插件

对接即梦平台生图的小工具

## 安装

1. 确保安装了 nodejs 环境。下载地址：https://nodejs.cn/download/ 。22以上的版本即可，推荐长期支持版本。
2. 进入项目目录，运行 init.bat 安装依赖。
3. 在Comfyui的python环境下执行：pip install -r requirements.txt
4. 因为即梦时国内网站，建议使用该插件时关闭代理软件。

## 使用

1. 执行工作流 [example-1.png](./docs/example-1.png)。第一次使用的时候会弹出即梦的首页，需要登录即梦账号，登录成功后页面会自动关闭，并继续执行工作流。
2. 工作流执行完成后，通常会输出4张图片（有时候因为网络原因，部分图片会下载失败）。