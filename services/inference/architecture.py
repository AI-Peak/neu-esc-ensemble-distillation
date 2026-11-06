"""The exact plain MTL/ED forward used by the research runner (no dropout)."""


def build_model(config, num_labels):
    import torch.nn as nn
    from transformers import AutoModel

    class Linear2Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = AutoModel.from_config(config, trust_remote_code=False)
            hidden = config.hidden_size
            self.fc_input = nn.Linear(hidden, hidden)
            self.activation = nn.SiLU()
            self.ln1 = nn.LayerNorm(hidden)
            self.out_sent = nn.Linear(hidden, num_labels["sentiment"])
            self.out_clas = nn.Linear(hidden, num_labels["topic"])

        def forward(self, input_ids, attention_mask):
            cls = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0, :]
            embedded = self.ln1(self.activation(self.fc_input(cls)))
            return self.out_sent(embedded), self.out_clas(embedded)

    return Linear2Head()
