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
        """テキストからマインドマップのデータを生成"""
        prompt = f"""
        以下のテキストから階層的なマインドマップを生成してください。
        以下の形式でJSON形式で出力してください：
        
        {{
            "center": "中心テーマ",
            "branches": [
                {{
                    "name": "メインブランチ1",
                    "sub_branches": ["サブブランチ1", "サブブランチ2"]
                }},
                // 他のブランチ...
            ]
        }}
        
        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # 文字列をJSON形式に変換する前に整形
            json_str = response.text.strip()
            # 最初と最後の```を削除（もし存在する場合）
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            elif json_str.startswith('```'):
                json_str = json_str[3:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            
            json_str = json_str.strip()
            
            try:
                # JSONとして解析
                mindmap_data = json.loads(json_str)
                
                # 必要なキーが存在するか確認
                if not isinstance(mindmap_data, dict):
                    raise ValueError("マインドマップデータが辞書形式ではありません")
                if "center" not in mindmap_data:
                    raise ValueError("中心テーマが見つかりません")
                if "branches" not in mindmap_data or not isinstance(mindmap_data["branches"], list):
                    raise ValueError("ブランチデータが正しい形式ではありません")
                
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
            
            # ノードとエッジの追加
            center = mindmap_data['center']
            G.add_node(center)
            
            # 色の設定
            node_colors = ['#1B365D']  # 中心ノードの色
            edge_colors = []
            
            # 各ブランチの追加
            for i, branch in enumerate(mindmap_data['branches']):
                G.add_node(branch['name'])
                G.add_edge(center, branch['name'])
                node_colors.append('#4A90E2')
                edge_colors.append('#8AB4F8')
                
                # サブブランチの追加
                for sub in branch['sub_branches']:
                    G.add_node(sub)
                    G.add_edge(branch['name'], sub)
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
                text=list(G.nodes()),
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
