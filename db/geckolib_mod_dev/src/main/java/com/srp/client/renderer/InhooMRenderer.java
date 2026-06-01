package com.srp.client.renderer;

import com.srp.client.model.InhooMModel;
import com.srp.entity.InhooMEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InhooMRenderer extends GeoEntityRenderer<InhooMEntity> {

    public InhooMRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InhooMModel());
    }
}
