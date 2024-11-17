import networkx as nx
import plotly.graph_objects as go
import google.generativeai as genai
import os
import io
import json
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def generate_mindmap(self, text, max_retries=3):
        """Generate mindmap data from text using Gemini API with retry mechanism"""
        for attempt in range(max_retries):
            try:
                logger.info(f"マインドマップ生成を試行中... (試行: {attempt + 1}/{max_retries})")
                return self._generate_mindmap_internal(text)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"API制限に達しました。{wait_time}秒後に再試行します...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"マインドマップの生成に失敗しました (試行: {attempt + 1}/{max_retries}): {error_str}")
                raise Exception(f"マインドマップの生成中にエラーが発生しました。しばらく待ってから再度お試しください。: {error_str}")

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation"""
        prompt = f"""
        以下のテキストから階層的なマインドマップを生成してください。
        以下の形式でJSON形式で出力してください：
        
        {{
            "center": "中心テーマ",
            "branches": [
                {{
                    "name": "メインブランチ1",
                    "sub_branches": ["サブブランチ1", "サブブランチ2"]
                }}
            ]
        }}
        
        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # Clean and validate JSON string
            json_str = response.text.strip()
            # Remove markdown code blocks if present
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            elif json_str.startswith('```'):
                json_str = json_str[3:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            
            json_str = json_str.strip()
            
            # Remove any control characters and escape sequences
            json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')
            
            try:
                mindmap_data = json.loads(json_str)
                
                # Validate structure
                if not isinstance(mindmap_data, dict):
                    raise ValueError("マインドマップデータが辞書形式ではありません")
                if "center" not in mindmap_data:
                    raise ValueError("中心テーマが見つかりません")
                if "branches" not in mindmap_data or not isinstance(mindmap_data["branches"], list):
                    raise ValueError("ブランチデータが正しい形式ではありません")
                
                return mindmap_data
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析エラー: {str(e)}")
                logger.error(f"解析対象の文字列: {json_str}")
                raise ValueError(f"マインドマップデータのJSON解析に失敗しました: {str(e)}")
                
        except Exception as e:
            error_msg = f"マインドマップの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def create_visualization(self, mindmap_data):
        """Create plotly visualization from mindmap data"""
        try:
            G = nx.Graph()
            
            # Generate unique node IDs
            node_id = 0
            node_mapping = {}
            
            # Add center node
            center = mindmap_data['center']
            node_mapping[node_id] = center
            G.add_node(node_id, label=center)
            center_id = node_id
            node_id += 1
            
            # Set colors
            node_colors = ['#1B365D']  # Center node color
            edge_colors = []
            
            # Add branches
            for branch in mindmap_data['branches']:
                # Add main branch
                node_mapping[node_id] = branch['name']
                G.add_node(node_id, label=branch['name'])
                G.add_edge(center_id, node_id)
                branch_id = node_id
                node_id += 1
                node_colors.append('#4A90E2')  # Main branch color
                edge_colors.append('#8AB4F8')  # Edge color
                
                # Add sub-branches
                for sub in branch['sub_branches']:
                    node_mapping[node_id] = sub
                    G.add_node(node_id, label=sub)
                    G.add_edge(branch_id, node_id)
                    node_id += 1
                    node_colors.append('#7FB3D5')  # Sub-branch color
                    edge_colors.append('#8AB4F8')  # Edge color
            
            # Calculate layout
            pos = nx.spring_layout(G)
            
            # Create edge traces
            edge_trace = []
            for edge in G.edges():
                x0, y0 = pos[edge[0]]
                x1, y1 = pos[edge[1]]
                edge_trace.append(
                    go.Scatter(
                        x=[x0, x1], y=[y0, y1],
                        line=dict(width=2, color='#8AB4F8'),
                        hoverinfo='none',
                        mode='lines'
                    )
                )
            
            # Create node trace
            node_trace = go.Scatter(
                x=[pos[node][0] for node in G.nodes()],
                y=[pos[node][1] for node in G.nodes()],
                mode='markers+text',
                marker=dict(
                    size=30,
                    color=node_colors,
                    line_width=2
                ),
                text=[G.nodes[node]['label'] for node in G.nodes()],
                textposition="middle center",
                textfont=dict(
                    family='Noto Sans JP, sans-serif',
                    size=12,
                    color='#1a365d'
                ),
                hoverinfo='text'
            )
            
            # Create layout
            layout = go.Layout(
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                width=800,
                height=600,
                font=dict(
                    family='Noto Sans JP, sans-serif',
                    size=12,
                    color='#1a365d'
                )
            )
            
            # Create figure
            fig = go.Figure(data=edge_trace + [node_trace], layout=layout)
            return fig
            
        except Exception as e:
            error_msg = f"マインドマップの可視化中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
