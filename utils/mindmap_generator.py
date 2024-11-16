import networkx as nx
import plotly.graph_objects as go
import google.generativeai as genai
import os
import io
import json

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def generate_mindmap(self, text):
        try:
            prompt = f"""
            以下のテキストから階層的なマインドマップを生成してください。
            以下の形式で出力してください（コメントは含めないでください）：
            
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
            
            response = self.model.generate_content(prompt)
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # コードブロックとコメントを除去
            json_str = response.text.strip()
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            elif json_str.startswith('```'):
                json_str = json_str[3:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            
            # コメント行を除去
            json_str = '\n'.join([line for line in json_str.split('\n') if not line.strip().startswith('//')])
            
            try:
                mindmap_data = json.loads(json_str.strip())
                return mindmap_data
            except json.JSONDecodeError as e:
                print(f"JSON解析エラー: {str(e)}")
                print(f"解析対象の文字列: {json_str}")
                raise ValueError(f"マインドマップデータのJSON解析に失敗しました: {str(e)}")
                
        except Exception as e:
            error_msg = f"マインドマップの生成中にエラーが発生しました: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)

    def create_visualization(self, mindmap_data):
        """マインドマップの可視化を生成"""
        try:
            G = nx.Graph()
            
            # 一意のノードIDを生成
            node_id = 0
            node_mapping = {}
            
            # 中心ノードの追加
            center = mindmap_data['center']
            node_mapping[node_id] = center
            G.add_node(node_id, label=center)
            center_id = node_id
            node_id += 1
            
            # 色の設定
            node_colors = ['#1B365D']
            edge_colors = []
            
            # 各ブランチの追加
            for branch in mindmap_data['branches']:
                # メインブランチの追加
                node_mapping[node_id] = branch['name']
                G.add_node(node_id, label=branch['name'])
                G.add_edge(center_id, node_id)
                branch_id = node_id
                node_id += 1
                node_colors.append('#4A90E2')
                edge_colors.append('#8AB4F8')
                
                # サブブランチの追加
                for sub in branch['sub_branches']:
                    node_mapping[node_id] = sub
                    G.add_node(node_id, label=sub)
                    G.add_edge(branch_id, node_id)
                    node_id += 1
                    node_colors.append('#7FB3D5')
                    edge_colors.append('#8AB4F8')
            
            # レイアウトの計算
            pos = nx.spring_layout(G)
            
            # プロットの作成
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
                hoverinfo='text'
            )
            
            # レイアウトの設定
            layout = go.Layout(
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                width=800,
                height=600
            )
            
            # 図の作成
            fig = go.Figure(data=edge_trace + [node_trace], layout=layout)
            return fig
            
        except Exception as e:
            error_msg = f"マインドマップの可視化中にエラーが発生しました: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
